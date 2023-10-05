from pathlib import Path

import numpy as np
import soundfile as sf

from recs import DType
from recs.audio.file_opener import FileOpener
from recs.audio.file_types import Format, Subtype

EXCLUSIONS = {(Format.AIFF, 'alaw')}
BLOCK = np.empty(shape=(4096, 2), dtype=DType)

# These cause a Python crash in external C code...!
CRASH_SUBTYPES = {Subtype.ULAW, Subtype.ALAW}
CRASH_SUBTYPES_FORMAT = {
    Format.MP3: {Subtype.MPEG_LAYER_III},
}
KWARGS = {'samplerate': 48_000, 'channels': 2}
ALLOWED = [(f, Subtype[s]) for f in Format for s in sf.available_subtypes(f).keys()]


def _writes(format, subtype):
    if subtype in (CRASH_SUBTYPES | CRASH_SUBTYPES_FORMAT.get(format, set())):
        return False

    opener = FileOpener(format=format, subtype=subtype, **KWARGS)
    try:
        with opener.open(Path(f'file.{format}'), 'w') as fp:
            fp.write(BLOCK)
        return True
    except Exception:
        if True:
            raise
        return False


def write_mp3_file(
    dtype='int32', suffix='.mp3', length=4096, channels=2, count=1, **ka
):
    import numpy as np
    import soundfile as sf

    f = f'test{suffix}'
    with sf.SoundFile(f, mode='w', channels=channels, samplerate=48_000, **ka) as fp:
        for i in range(count):
            fp.write(np.empty(shape=(length, channels), dtype=dtype))
