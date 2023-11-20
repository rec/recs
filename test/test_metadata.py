import json
import sys

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.base import RecsError
from recs.cfg.metadata import RECS_USES, UNUSABLE, USABLE, get_metadata, to_dict

CHANGED = {'license', 'software'}
WAV_FILE = 'metadata.wav'
METADATA = {k: k.capitalize() for k in USABLE | RECS_USES}


def test_unchanged():
    assert set(sf._str_types) == RECS_USES | USABLE | UNUSABLE
    assert not (CHANGED & USABLE)


def write_metadata(
    filename=WAV_FILE, metadata=METADATA, channels=2, samplerate=48_000, time=1
):
    fp = sf.SoundFile(
        filename, mode='w', channels=channels, samplerate=samplerate, subtype='PCM_32'
    )
    for k, v in metadata.items():
        assert k in sf._str_types
        setattr(fp, k, v)

    with fp:
        fp.write(np.empty(shape=(time * samplerate, channels), dtype='int32'))
        return get_metadata(fp)


@tdir
def test_writing_metadata():
    write_metadata()

    with sf.SoundFile(WAV_FILE) as fp:
        full = {k: getattr(fp, k, None) for k in sf._str_types}
        actual = {k: v for k, v, in full.items() if k not in CHANGED}
        expected = {k: k.capitalize() for k in actual}
        assert actual == expected
        assert full['software'].startswith('Software')
        full['license']  # It's '' but no need to assert that


def test_to_dict():
    assert to_dict([]) == {}
    assert to_dict(['album = Mr Bungle ']) == {'album': 'Mr Bungle'}
    assert to_dict(['album = Alb', 'title=Oof']) == {'album': 'Alb', 'title': 'Oof'}


def test_to_dict_error():
    with pytest.raises(RecsError) as e:
        to_dict('albom=x album=y album title=tt title=tt license=Artistic'.split())
    print(*e.value.args)

    msg = (
        "Metadata: unknown: ['albom=x'], malformed: ['album'], "
        "duplicate: ['title=tt'], not settable: ['license=Artistic']"
    )
    assert e.value.args == (msg,)


def main():
    for a in sys.argv[1:]:
        print(a)
        try:
            with sf.SoundFile(a) as fp:
                md = {k: v for k in sf._str_types if (v := getattr(fp, k, None))}
                print(json.dumps(md, indent=4))

        except Exception as e:
            print('ERROR', e)


if __name__ == '__main__':
    main()
