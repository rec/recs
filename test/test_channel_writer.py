import dataclasses as dc

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.audio.track import Track
from recs.base.cfg import Cfg
from recs.base.times import Times
from recs.base.types import SDTYPE, Format, SdType, Subtype

SAMPLERATES = 44_100, 48_000
TIMES = {'silence_before_start': 30, 'silence_after_end': 40, 'stop_after_silence': 50}

II = [np.array((1, -1, 1, -1), dtype=SDTYPE)]
OO = [np.array((0, 0, 0, 0), dtype=SDTYPE)]


@dc.dataclass
class Case:
    arrays: np.ndarray
    result: list[list[int]]
    format: Format = Format.wav
    longest_file_time: int = 0
    sdtype: SdType | None = None

    replace = dc.replace


BASE = Case(
    arrays=(17 * OO) + (4 * II) + (40 * OO) + II + (51 * OO) + (19 * II),
    result=[[28, 16, 12], [28, 4, 12], [28, 76]],
)
SIMPLE = Case(
    arrays=100 * II,
    longest_file_time=210,
    result=[[0, 210], [0, 190]],
)


TEST_CASES = (
    BASE,
    BASE.replace(sdtype=SdType.int16),
    BASE.replace(sdtype=SdType.int32),
    BASE.replace(sdtype=SdType.float32),
    BASE.replace(sdtype=SdType.int24),
    Case(
        arrays=(4 * II) + (3 * OO) + II + (2000 * OO) + (3 * II),
        result=[[0, 16, 12, 4, 12], [28, 12]],
    ),
    SIMPLE,
    SIMPLE.replace(format=Format.flac),
    SIMPLE.replace(format=Format.mp3),
    BASE.replace(format=Format.caf),
)


@pytest.mark.parametrize('case', TEST_CASES)
@tdir
def test_channel_writer(case, mock_devices):
    track = Track('Ext', '2')
    times = Times[int](longest_file_time=case.longest_file_time, **TIMES)

    cfg = Cfg(format=case.format, sdtype=case.sdtype)
    with ChannelWriter(cfg, times=times, track=track) as writer:
        [writer.write(Block(a)) for a in case.arrays]

    files = sorted(writer.files_written)
    suffix = '.' + case.format
    assert all(f.suffix == suffix for f in files)

    contents, samplerates = zip(*(sf.read(f) for f in files))

    assert all(s in SAMPLERATES for s in samplerates)
    result = [list(_on_and_off_segments(c)) for c in contents]
    assert case.result == result

    with sf.SoundFile(files[0]) as fp:
        if case.sdtype == SdType.int24:
            assert fp.subtype.lower() == Subtype.pcm_24

        if case.sdtype == SdType.float32:
            assert fp.subtype.lower() == Subtype.float

        if case.format == Format.mp3:
            assert fp.date == '2023'
            assert fp.software == ''
        else:
            assert fp.date == '2023-10-15T16:49:21.000502'
            assert fp.software.startswith('https://github.com/rec/recs')


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
