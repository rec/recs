from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs import RECS
from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.audio.file_types import DTYPE
from recs.audio.track import Track
from recs.misc.times import Times

II = [np.array((1, -1, 1, -1), dtype=DTYPE)]
OO = [np.array((0, 0, 0, 0), dtype=DTYPE)]

ARRAYS1 = (17 * OO) + (4 * II) + (40 * OO) + II + (51 * OO) + (19 * II)
RESULT1 = [[28, 16, 12], [28, 4, 12], [28, 76]]

ARRAYS2 = (4 * II) + (3 * OO) + II + (2000 * OO) + (3 * II)
RESULT2 = [[0, 16, 12, 4, 12], [28, 12]]

ARRAYS3 = 100 * II
RESULT3 = [[0, 210], [0, 190]]

SAMPLERATE = 48_000

TESTS = ((ARRAYS1, RESULT1, 0), (ARRAYS2, RESULT2, 0), (ARRAYS3, RESULT3, 210))
TIMES = {'silence_before_start': 30, 'silence_after_end': 40, 'stop_after_silence': 50}


@pytest.mark.parametrize('arrays, segments, longest_file_time', TESTS)
@tdir
def test_channel_writer(arrays, segments, longest_file_time, mock_devices, monkeypatch):
    monkeypatch.setattr(RECS, 'format', 'wav')
    track = Track('Ext', '2')
    times = Times[int](longest_file_time=longest_file_time, **TIMES)

    with ChannelWriter(samplerate=SAMPLERATE, times=times, track=track) as writer:
        [writer.write(Block(a)) for a in arrays]

    contents, samplerates = zip(*(sf.read(f) for f in sorted(Path('.').iterdir())))

    assert all(s == SAMPLERATE for s in samplerates)
    assert segments == [list(_on_and_off_segments(c)) for c in contents]


def _on_and_off_segments(it):
    pb = False
    pi = 0

    if it := list(it):
        for i, x in enumerate(it):
            if (b := bool(x)) != pb:
                yield i - pi
                pb = b
                pi = i
        yield i + 1 - pi
