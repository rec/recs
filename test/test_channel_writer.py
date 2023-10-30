import dataclasses as dc
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

SAMPLERATES = 44_100, 48_000
TIMES = {'silence_before_start': 30, 'silence_after_end': 40, 'stop_after_silence': 50}

II = [np.array((1, -1, 1, -1), dtype=DTYPE)]
OO = [np.array((0, 0, 0, 0), dtype=DTYPE)]


@dc.dataclass
class Case:
    arrays: np.ndarray
    result: list[list[int]]
    longest_file_time: int = 0


TEST_CASES = (
    Case(
        arrays=(17 * OO) + (4 * II) + (40 * OO) + II + (51 * OO) + (19 * II),
        result=[[28, 16, 12], [28, 4, 12], [28, 76]],
    ),
    Case(
        arrays=(4 * II) + (3 * OO) + II + (2000 * OO) + (3 * II),
        result=[[0, 16, 12, 4, 12], [28, 12]],
    ),
    Case(
        arrays=100 * II,
        result=[[0, 210], [0, 190]],
        longest_file_time=210,
    ),
)


@pytest.mark.parametrize('case', TEST_CASES)
@tdir
def test_channel_writer(case, mock_devices, monkeypatch):
    monkeypatch.setattr(RECS, 'format', 'wav')
    track = Track('Ext', '2')
    times = Times[int](longest_file_time=case.longest_file_time, **TIMES)

    with ChannelWriter(times=times, track=track) as writer:
        [writer.write(Block(a)) for a in case.arrays]

    contents, samplerates = zip(*(sf.read(f) for f in sorted(Path('.').iterdir())))

    assert all(s in SAMPLERATES for s in samplerates)
    assert case.result == [list(_on_and_off_segments(c)) for c in contents]


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
