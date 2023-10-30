import dataclasses as dc
import os

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.audio.file_types import SDTYPE, Format, SdType
from recs.audio.track import Track
from recs.misc.times import Times

SAMPLERATES = 44_100, 48_000
TIMES = {'silence_before_start': 30, 'silence_after_end': 40, 'stop_after_silence': 50}

II = [np.array((1, -1, 1, -1), dtype=SDTYPE)]
OO = [np.array((0, 0, 0, 0), dtype=SDTYPE)]

RECS_INTEGRATION_TEST = 'RECS_INTEGRATION_TEST' in os.environ


@dc.dataclass
class Case:
    arrays: np.ndarray
    result: list[list[int]]
    format: Format = Format.wav
    longest_file_time: int = 0

    replace = dc.replace


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
        longest_file_time=210,
        result=[[0, 210], [0, 190]],
    ),
    Case(
        arrays=100 * II,
        longest_file_time=210,
        result=[[0, 210], [0, 190]],
    ),
    Case(
        arrays=100 * II,
        format=Format.flac,
        longest_file_time=210,
        result=[[0, 210], [0, 190]],
    ),
    Case(
        arrays=100 * II,
        format=Format.mp3,
        longest_file_time=210,
        result=[[0, 210], [0, 190]],
    ),
    Case(
        arrays=(17 * OO) + (4 * II) + (40 * OO) + II + (51 * OO) + (19 * II),
        format=Format.caf,
        result=[[28, 16, 12], [28, 4, 12], [28, 76]],
    ),
)


@pytest.mark.parametrize('case', TEST_CASES)
@tdir
def test_channel_writer(case, mock_devices, set_recs):
    set_recs(format=case.format)

    track = Track('Ext', '2')
    times = Times[int](longest_file_time=case.longest_file_time, **TIMES)

    with ChannelWriter(times=times, track=track) as writer:
        [writer.write(Block(a)) for a in case.arrays]

    files = sorted(writer.files_written)
    suffix = '.' + case.format
    assert all(f.suffix == suffix for f in files)

    contents, samplerates = zip(*(sf.read(f) for f in files))

    assert all(s in SAMPLERATES for s in samplerates)
    result = [list(_on_and_off_segments(c)) for c in contents]
    assert case.result == result


@pytest.mark.skipif(not RECS_INTEGRATION_TEST, reason='Very long test')
@tdir
def test_long_wav(mock_devices, set_recs):
    set_recs(format=Format.wav, sdtype=SdType.float32)

    TARGET = 0x1_0008_0000
    COUNT = 4

    size = int(TARGET / COUNT / 4)
    size -= size % 8

    rng = np.random.default_rng(seed=723)
    a = rng.uniform(-0x100, 0x100, (size, 2)).astype('float32')

    block = Block(a)
    track = Track('Ext', '1-2')
    times = Times[int](**TIMES)

    with ChannelWriter(times=times, track=track) as writer:
        for i in range(COUNT):
            print('Writing', i + 1, 'of', COUNT)
            writer.write(block)
    files = writer.files_written
    assert len(files) == 2
    sizes = [os.path.getsize(f) for f in files]
    big = 0x1_0000_0000
    assert big - 0x100 < sizes[0] <= big

    assert TARGET < sum(sizes) <= TARGET + 0x80


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
