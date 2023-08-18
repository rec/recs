from . import field
from .block import Block
from collections import defaultdict
import dataclasses as dc
import numbers
import time

from .counter import Accumulator, Counter

from rich.table import Table

COLUMNS = (
    'time',
    'device',
    'channel',
    'count',
    'block',
    'rms',
    'rms_mean',
    'amplitude',
    'amplitude_mean',
)


@dc.dataclass
class Channel:
    block_count: Counter = field(Counter)
    amplitude: Accumulator = field(Accumulator)
    rms: Accumulator = field(Accumulator)

    def __call__(self, block):
        self.block_count()
        self.rms(block.rms)
        self.amplitude(block.amplitude)

    def rows(self, channel):
        yield {
            'amplitude': self.amplitude.value,
            'amplitude_mean': self.amplitude.mean(),
            'channel': channel,
            'count': self.block_count.value,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }


@dc.dataclass
class Device:
    block_count: Counter = field(Counter)
    block_size: Accumulator = field(Accumulator)
    channels: dict[str, Channel] = field(lambda: defaultdict(Channel))

    def __call__(self, frame, channel_name):
        self.block_count()
        block = Block(frame)
        assert block.channels <= 2, f'{len(block)=}, {block.channels=}'
        self.block_size(len(block))
        self.channels[channel_name](block)

    def rows(self, name):
        yield {
            'block': self.block_size.value,
            'count': self.block_count.value,
            'device': name,
        }
        for k, v in self.channels.items():
            yield from v.rows(k)


@dc.dataclass
class Global:
    block_count: Counter = field(Counter)
    start_time: float = field(time.time)
    devices: dict[str, Device] = field(lambda: defaultdict(Device))

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    def __call__(self, frame, channel_name, device):
        # print('global')
        self.block_count()
        self.devices[device.name](frame, channel_name)

    def table(self):
        t = Table(*COLUMNS)
        for row in self.rows():
            t.add_row(*(_to_str(row.get(c, ''), c) for c in COLUMNS))

        return t

    def rows(self):
        yield {
            'time': f'{self.elapsed_time:9.3f}',
            'count': self.block_count.value,
        }
        for k, v in self.devices.items():
            yield from v.rows(k)


RED = 256 // 3
GREEN = 512 // 3
BLUE = 0


def _to_str(x, c) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, numbers.Integral):
        if c in ('count', 'block'):
            global RED, GREEN, BLUE
            RED = (RED + 1) % 256
            GREEN = (GREEN + 1) % 256
            BLUE = (BLUE + 1) % 256
            return f'[rgb({RED},{GREEN},{BLUE})]{x:>7,}'

    if isinstance(x, numbers.Real):
        return f'{x:6.1%}'
    assert len(x) <= 2, f'{len(x)}'
    return ' |'.join(_to_str(i, c) for i in x)
