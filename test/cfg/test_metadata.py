import json
import sys

import numpy as np
import pytest
import soundfile
import tdir

from recs.base import RecsError
from recs.base.types import Format
from recs.cfg import metadata

CHANGED = {'license', 'software'}
WAV_FILE = 'metadata.wav'
METADATA = {k: k.capitalize() for k in metadata.USABLE | metadata.RECS_USES}


def test_unchanged():
    assert (
        set(soundfile._str_types)
        == metadata.RECS_USES | metadata.USABLE | metadata.UNUSABLE
    )
    assert not (CHANGED & metadata.USABLE)


def write_metadata(
    filename=WAV_FILE,
    metadata_values=METADATA,
    channels=2,
    samplerate=48_000,
    subtype='PCM_32',
    dtype='int32',
):
    fp = soundfile.SoundFile(
        filename, mode='w', channels=channels, samplerate=samplerate, subtype=subtype
    )
    for k, v in metadata_values.items():
        assert k in soundfile._str_types
        setattr(fp, k, v)

    with fp:
        fp.write(np.empty(shape=(samplerate, channels), dtype=dtype))
        return metadata.get_metadata(fp)


@pytest.mark.parametrize('format', Format)
@tdir
def test_writing_metadata(format: Format):
    if format not in metadata.ALLOWS_METADATA:
        return

    filename = f'metadata.{format:s}'
    write_metadata(filename, subtype=None, dtype='int16')

    with soundfile.SoundFile(filename) as fp:
        full = {k: getattr(fp, k, None) for k in soundfile._str_types}
        print(full)
        actual = {k: v for k, v in full.items() if k not in CHANGED}
        expected = {k: k.capitalize() for k in actual}
        if format == Format.mp3:
            to_clear = ['copyright']
        else:
            to_clear = []
        expected.update({i: '' for i in to_clear})
        assert actual == expected
        if format != Format.mp3:
            assert full['software'].startswith('Software')
        full['license']  # It's '' but no need to assert that


def test_to_dict():
    assert metadata.to_dict([]) == {}
    assert metadata.to_dict(['album = Mr Bungle ']) == {'album': 'Mr Bungle'}
    assert metadata.to_dict(['album = Alb', 'title=Oof']) == {
        'album': 'Alb',
        'title': 'Oof',
    }


def test_to_dict_error():
    with pytest.raises(RecsError) as e:
        metadata.to_dict(
            'albom=x album=y album title=tt title=tt license=Artistic'.split()
        )
    print(*e.value.args)

    msg = (
        "unknown: ['albom=x'], malformed: ['album'], "
        "duplicate: ['title=tt'], not settable: ['license=Artistic']"
    )
    assert e.value.args == (msg,)


def main():
    for a in sys.argv[1:]:
        print(a)
        try:
            with soundfile.SoundFile(a) as fp:
                md = {k: v for k in soundfile._str_types if (v := getattr(fp, k, None))}
                print(json.dumps(md, indent=4))

        except Exception as e:
            print('ERROR', e)


if __name__ == '__main__':
    main()
