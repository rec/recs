import os
from test.cfg.test_metadata import METADATA, WAV_FILE, write_metadata

import pytest
import tdir

from recs.audio.header_size import header_size
from recs.base.types import Format

TCS = {'title': 'Title', 'copyright': 'Copyright', 'software': 'Software'}

CASES = (
    (WAV_FILE, {'title': 'Tit'}, 68),
    (WAV_FILE, {'title': 'Titl'}, 70),
    (WAV_FILE, {'title': 'Title'}, 70),
    (WAV_FILE, {'title': 'Title', 'copyright': 'Copyright'}, 88),
    (
        WAV_FILE,
        {'title': 'Title', 'copyright': 'Copyright', 'software': 'Software'},
        124,
    ),
    (
        WAV_FILE,
        {
            'title': 'Title',
            'copyright': 'Copyright',
            'software': 'Software',
            'artist': 'Artis',
        },
        138,
    ),
    (
        WAV_FILE,
        {
            'title': 'Title',
            'copyright': 'Copyright',
            'software': 'Software',
            'artist': 'Artist',
        },
        140,
    ),
    (WAV_FILE, METADATA, 218),
    (WAV_FILE, {}, 44),
    (WAV_FILE, {'title': 't'}, 66),
    (WAV_FILE, {'title': 'ti'}, 68),
    (WAV_FILE, {'copyright': 'c'}, 66),
    (WAV_FILE, {'copyright': 'c', 'title': 't'}, 76),
    (WAV_FILE, {'copyright': 'c', 'title': 't', 'date': 'd'}, 86),
    (WAV_FILE, {'software': 't'}, 86),
)
SAMPLERATE = 44100

_CASES = tuple((*i, channel) for channel in (1, 2) for i in CASES)


@pytest.mark.parametrize('filename, metadata, size, channels', _CASES)
@tdir
def test_header_size(filename, metadata, size, channels):
    write_metadata(filename, metadata, samplerate=SAMPLERATE, channels=channels)

    file_size = os.path.getsize(filename)
    base_size = SAMPLERATE * 4 * channels
    actual_size = file_size - base_size
    assert size == actual_size

    if filename.endswith('wav'):
        assert size == header_size(metadata, Format.wav), str(metadata)
