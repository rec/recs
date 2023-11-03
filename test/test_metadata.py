import json
import sys

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.audio.metadata import RECS_USES, UNUSABLE, USABLE, to_dict
from recs.misc import RecsError

CHANGED = {'license', 'software'}


def _get_metadata(fp):
    return {k: v for k in sf._str_types if (v := getattr(fp, k, None))}


def test_unchanged():
    assert set(sf._str_types) == RECS_USES | USABLE | UNUSABLE
    assert not (CHANGED & USABLE)


@tdir
def test_writing_metadata():
    f = sf.SoundFile(
        'meta.wav', mode='w', channels=2, samplerate=48_000, subtype='PCM_32'
    )
    for t in sf._str_types:
        setattr(f, t, t.capitalize())

    with f:
        f.write(np.empty(shape=(48_000, 2), dtype='int32'))

    with sf.SoundFile('meta.wav') as fp:
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
                print(json.dumps(_get_metadata(fp), indent=4))
        except Exception as e:
            print('ERROR', e)


if __name__ == '__main__':
    main()
