import os
from test.audio.test_channel_writer import TIMES

import numpy as np
import pytest
import tdir

from recs.audio import channel_writer
from recs.audio.block import Block
from recs.audio.file_opener import FileOpener
from recs.base.types import Format, SdType
from recs.cfg import Cfg
from recs.cfg.time_settings import TimeSettings

SAMPLERATE = 44_100
SHRINK = 256
MAX_WAV_SIZE = channel_writer.MAX_WAV_SIZE // SHRINK


@tdir
def test_one_long_file(mock_input_streams, monkeypatch):
    monkeypatch.setattr(channel_writer, 'MAX_WAV_SIZE', MAX_WAV_SIZE)
    print(f'\ntest_long: {Format.wav}')
    cfg = Cfg(
        formats=[Format.wav],
        metadata=[],
        sdtype=SdType.float32,
    )

    TOTAL_SIZE = MAX_WAV_SIZE - 0x1000
    COUNT = 4

    size = int(TOTAL_SIZE / COUNT / 4 / 2)
    size -= size % 8

    rng = np.random.default_rng(seed=723)
    print('Initializing...')
    a = rng.uniform(-0x100, 0x100, (size, 2))

    print('Converting...')
    a = a.astype('float32')

    block = Block(a)
    track = cfg.aliases.to_track('Ext + 1-2')
    times = TimeSettings[int](**TIMES)

    time = 0
    with channel_writer.ChannelWriter(cfg=cfg, times=times, track=track) as writer:
        assert writer.largest_file_size == channel_writer.MAX_WAV_SIZE
        for i in range(COUNT):
            print('Writing', i + 1, 'of', COUNT)
            writer._receive_block(block, time, writer.should_record(block))
            time += len(block) / SAMPLERATE
        writer._receive_block(block[:0x1000], time, writer.should_record(block))

    files = writer.files_written
    print(*files)
    sizes = [os.path.getsize(f) for f in files]
    print(*(hex(s) for s in sizes))
    assert len(files) == 2

    diff = channel_writer.MAX_WAV_SIZE - sizes[0]
    diff2 = sum(sizes) - TOTAL_SIZE

    print(hex(sizes[0]), hex(diff), hex(diff2))

    assert 0 <= diff <= 0x10000


@tdir
def test_file_header(mock_devices):
    fo = FileOpener(format=Format.wav)
    with fo.open('file.wav', {}, True) as fp:
        fp.write(np.zeros((8, 1), 'int32'))
