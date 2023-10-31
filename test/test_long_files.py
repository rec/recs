import os
from test.test_channel_writer import TIMES

import numpy as np
import pytest
import tdir

from recs import Cfg
from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.audio.file_types import Format, SdType
from recs.audio.track import Track
from recs.misc.times import Times

RECS_INTEGRATION_TEST = 'RECS_INTEGRATION_TEST' in os.environ


@pytest.mark.parametrize('format', (Format.aiff, Format.wav))
@pytest.mark.skipif(not RECS_INTEGRATION_TEST, reason='Very long test')
@tdir
def test_long_file(mock_devices, format):
    print(f'\ntest_long: {format}')
    cfg = Cfg(format=format, sdtype=SdType.float32)

    SIZE = 0x1_0000_0000 if format == Format.wav else 0x8000_0000
    TOTAL_SIZE = SIZE + 0x8_0000
    COUNT = 4

    size = int(TOTAL_SIZE / COUNT / 4 / 2)
    size -= size % 8

    rng = np.random.default_rng(seed=723)
    print('Initializing...')
    a = rng.uniform(-0x100, 0x100, (size, 2))

    print('Converting...')
    a = a.astype('float32')

    block = Block(a)
    track = Track('Ext', '1-2')
    times = Times[int](**TIMES)

    with ChannelWriter(cfg=cfg, times=times, track=track) as writer:
        for i in range(COUNT):
            print('Writing', i + 1, 'of', COUNT)
            writer.write(block)
    files = writer.files_written
    sizes = [os.path.getsize(f) for f in files]
    print(*(hex(s) for s in sizes))
    assert len(files) == 2

    diff = SIZE - sizes[0]
    diff2 = sum(sizes) - TOTAL_SIZE

    print(hex(sizes[0]), hex(diff), hex(diff2))

    assert diff == 0
    if format == Format.wav:
        assert diff2 == 0xB0
    else:
        assert diff2 == 0xD0