import os

import pytest
import tdir

from recs.audio.header_size import header_size
from recs.base.types import Format

from .test_metadata import METADATA, WAV_FILE, write_metadata

AIF_FILE = 'metadata.aiff'

TCS = {'title': 'Title', 'copyright': 'Copyright', 'software': 'Software'}

CASES = (
    (AIF_FILE, {}, 54),
    (AIF_FILE, (D := {'title': 'Title'}), 68),
    (AIF_FILE, (D := D | {'copyright': 'Copyright'}), 86),
    # Adding fields does not change the size!!!
    (AIF_FILE, (D := D | {'software': 'Software'}), 126),
    (AIF_FILE, (D := D | {'date': '1984'}), 126),
    (AIF_FILE, (D := D | {'tracknumber': '10'}), 126),
    (AIF_FILE, METADATA, 156),
    #
    (AIF_FILE, {'title': 'Title'}, 68),
    (AIF_FILE, {'title': 'Title', 'copyright': 'Copyright'}, 86),
    (
        AIF_FILE,
        {'title': 'Title', 'copyright': 'Copyright', 'software': 'Softwar'},
        124,
    ),
    (AIF_FILE, {'software': 'Softwar'}, 92),
    (AIF_FILE, {'software': 'Software'}, 94),
    (AIF_FILE, TCS, 126),
    #
    (AIF_FILE, METADATA, 156),
    #
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
    #
    (AIF_FILE, {}, 54),
    (AIF_FILE, {'title': 't'}, 64),
    (AIF_FILE, {'copyright': 'c'}, 64),
    (AIF_FILE, {'copyright': 'c', 'title': 't'}, 74),
    (AIF_FILE, {'copyright': 'c', 'title': 't', 'artist': 'a'}, 84),
    (AIF_FILE, {'software': 't'}, 86),
    #
    (AIF_FILE, {'title': 'title'}, 68),
    # (AIF_FILE, METADATA, 156),
    #
    (WAV_FILE, {}, 44),
    (WAV_FILE, {'title': 't'}, 66),
    (WAV_FILE, {'title': 'ti'}, 68),
    (WAV_FILE, {'copyright': 'c'}, 66),
    (WAV_FILE, {'copyright': 'c', 'title': 't'}, 76),
    (WAV_FILE, {'copyright': 'c', 'title': 't', 'date': 'd'}, 86),
    (WAV_FILE, {'software': 't'}, 86),
)
SAMPLERATE = 44100


@pytest.mark.parametrize('filename, metadata, size', CASES)
@tdir
def test_header_size(filename, metadata, size):
    write_metadata(filename, metadata, samplerate=SAMPLERATE)

    file_size = os.path.getsize(filename)
    base_size = SAMPLERATE * 4 * 2
    actual_size = file_size - base_size
    assert size == actual_size

    if filename.endswith('wav'):
        assert size == header_size(metadata, Format.wav), str(metadata)
    else:
        # Something is restricting header sizes here, but it isn't an absolute cap
        assert size <= header_size(metadata, Format.aiff), str(metadata)
