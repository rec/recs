from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir

import recs.audio.file_types
from recs.audio import block
from recs.audio.channel_writer import ChannelWriter
from recs.audio.file_creator import FileCreator
from recs.audio.file_opener import FileOpener
from recs.audio.file_types import Subtype
from recs.audio.times import Times
from recs.ui.track import Track

I = [np.array((1, -1, 1, -1), dtype=recs.audio.file_types.DTYPE)]  # noqa: E741
O = [np.array((0, 0, 0, 0), dtype=recs.audio.file_types.DTYPE)]  # noqa: E741

ARRAYS1 = (17 * O) + (4 * I) + (40 * O) + I + (51 * O) + (19 * I)
RESULT1 = [[28, 16, 12], [28, 4, 12], [28, 76]]
ARRAYS2 = (4 * I) + (3 * O) + I + (2000 * O) + (3 * I)
RESULT2 = [[0, 16, 12, 4, 12], [28, 12]]
SAMPLERATE = 48_000

TIMES = Times[int](silence_before_start=30, silence_after_end=40, stop_after_silence=50)
OPENER = FileOpener(channels=1, samplerate=SAMPLERATE, subtype=Subtype.pcm_24)


@pytest.mark.parametrize('arrays, segments', [(ARRAYS1, RESULT1), (ARRAYS2, RESULT2)])
@tdir
def test_channel_writer(arrays, segments, mock_devices):
    CREATOR = FileCreator(opener=OPENER, path=Path('.'), track=Track('Ext', '2'))

    with ChannelWriter(creator=CREATOR, times=TIMES) as writer:
        [writer.write(block.Block(a)) for a in arrays]

    contents, samplerates = zip(*(sf.read(f) for f in sorted(Path('.').iterdir())))

    assert all(s == SAMPLERATE for s in samplerates)
    assert segments == [list(_segments(c)) for c in contents]


def _segments(it):
    pb = False
    pi = 0

    for i, x in enumerate(it):
        if (b := bool(x)) != pb:
            yield i - pi
            pb = b
            pi = i
    yield i + 1 - pi
