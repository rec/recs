from pathlib import Path

import numpy as np
import soundfile as sf
import tdir

from recs import DType
from recs.audio.file_opener import FileOpener
from recs.audio.file_types import Format, Subtype
from recs.audio.valid_subtypes import VALID_SUBTYPES

EXCLUSIONS = {(Format.AIFF, 'alaw')}
BLOCK = np.empty(shape=(4092, 2), dtype=DType)

# These cause a Python crash in external C code...!
CRASH_SUBTYPES = {Subtype.ULAW, Subtype.ALAW}
CRASH_SUBTYPES_FORMAT = {
    Format.MP3: {Subtype.MPEG_LAYER_III},
}
KWARGS = {'samplerate': 48_000, 'channels': 2}
ALLOWED = [(f, Subtype[s]) for f in Format for s in sf.available_subtypes(f)]


def _writes(format, subtype):
    if subtype in (CRASH_SUBTYPES | CRASH_SUBTYPES_FORMAT.get(format, set())):
        return False

    opener = FileOpener(_check=False, format=format, subtype=subtype, **KWARGS)
    try:
        with opener.open(Path(f'file.{format}'), 'w') as fp:
            fp.write(BLOCK)
        return True
    except Exception:
        return False


@tdir
def test_format_subtype():
    ok, errors = [], []

    for format, subtype in ALLOWED:
        if _writes(format, subtype):
            ok.append([format, subtype])
        else:
            errors.append([format, subtype])

    assert len(ok) == 96
    assert len(errors) == 56  # Should be zero!


@tdir
def test_format_subtype_correct():
    ok = {}

    for format, subtype in ALLOWED:
        if _writes(format, subtype):
            ok.setdefault(format, []).append(subtype.lower())

    import json

    print(json.dumps(ok, indent=4))

    assert ok == VALID_SUBTYPES


@tdir
def test_format_subtype_correct_more():
    def accept(format, subtype):
        try:
            FileOpener(format=format, subtype=subtype)
            return True
        except ValueError:
            return False

    accepts = [accept(f, s) for f, s in ALLOWED]
    writes = [_writes(f, s) for f, s in ALLOWED]

    assert accepts == writes


if __name__ == '__main__':
    test_format_subtype_correct()
