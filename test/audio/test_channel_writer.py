import dataclasses as dc
from test import conftest

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.base.types import SDTYPE, Format, SdType, Subtype
from recs.cfg import Cfg
from recs.cfg.time_settings import TimeSettings

SAMPLERATE = 44_100
TIMES = {'quiet_before_start': 30, 'quiet_after_end': 40, 'stop_after_quiet': 50}

II = [np.array((1, -1, 1, -1), dtype=SDTYPE)]
OO = [np.array((0, 0, 0, 0), dtype=SDTYPE)]


@dc.dataclass
class Case:
    arrays: np.ndarray
    result: list[list[int]]
    format: Format = Format.wav
    longest_file_time: int = 0
    name: str = ''
    sdtype: SdType | None = None
    shortest_file_time: int = 1

    replace = dc.replace


BASE = Case(
    name='base',
    arrays=(17 * OO) + (4 * II) + (40 * OO) + II + (51 * OO) + (19 * II),
    result=[[28, 16, 12], [28, 4, 12], [28, 76]],
)
LONGEST_FILE_TIME = Case(
    name='longest_file_time',
    arrays=100 * II,
    longest_file_time=210,
    result=[[0, 208], [0, 192]],
)


TEST_CASES = (
    BASE,
    BASE.replace(sdtype=SdType.int16),
    BASE.replace(sdtype=SdType.int32),
    BASE.replace(sdtype=SdType.float32),
    Case(
        name='not sure',
        arrays=(4 * II) + (3 * OO) + II + (2000 * OO) + (3 * II),
        result=[[0, 16, 12, 4, 12], [28, 12]],
    ),
    LONGEST_FILE_TIME,
    LONGEST_FILE_TIME.replace(format=Format.flac),
    LONGEST_FILE_TIME.replace(format=Format.wav),
    LONGEST_FILE_TIME.replace(format=Format.mp3),
    BASE.replace(format=Format.caf),
)


@pytest.mark.parametrize('case', TEST_CASES)
@tdir
def test_channel_writer(case, mock_devices):
    cfg = Cfg(format=case.format, sdtype=case.sdtype)
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        longest_file_time=case.longest_file_time,
        shortest_file_time=case.shortest_file_time,
        **TIMES,
    )

    timestamp = conftest.TIMESTAMP
    with ChannelWriter(cfg, times=times, track=track) as writer:
        for a in case.arrays:
            b = Block(a)
            writer._receive_block(b, timestamp)
            timestamp += len(b) / SAMPLERATE

    files = sorted(writer.files_written)
    suffix = '.' + case.format
    assert all(f.suffix == suffix for f in files)

    contents, samplerates = zip(*(sf.read(f) for f in files))

    assert all(s == SAMPLERATE for s in samplerates)
    result = [list(_on_and_off_segments(c)) for c in contents]
    assert case.result == result

    with sf.SoundFile(files[0]) as fp:
        if case.sdtype == SdType.float32:
            assert fp.subtype.lower() == Subtype.float

        if case.format == Format.mp3:
            assert fp.date == '2023'
            assert fp.software == ''
        else:
            assert fp.date.startswith('2023-10-15T16:49:21')
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
