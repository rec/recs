from . import device, field, mux
from .block import Block
from collections import defaultdict
import dataclasses as dc
import numbers
import time
from test import mock_data

from .counter import Accumulator, Counter

from rich.live import Live
from rich.table import Table

II = mock_data.II

DEVICE_SLICES = {'FLOW': mux.auto_slice(8) | {'Main': slice(8, 10)}}

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


def check():
    g = Global()
    with Live(g.table(), refresh_per_second=4) as live:
        for i, block in enumerate(mock_data.emit_blocks()):
            g(*block)
            if not (i % 20):
                live.update(g.table())


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

    def __call__(self, frame, channel_name, device_name):
        self.block_count()
        self.devices[device_name](frame, channel_name)

    def table(self):
        t = Table(*COLUMNS)
        for row in self.rows():
            t.add_row(*(_to_str(row.get(c, ''), c) for c in COLUMNS))

        return t

    def rows(self):
        yield {
            'time': f'{self.elapsed_time:10.03}',
            'count': self.block_count.value,
        }
        for k, v in self.devices.items():
            yield from v.rows(k)


def _to_str(x, c) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, numbers.Integral):
        if c in ('count', 'block'):
            return str(x)
    if c.startswith('amplitude'):
        div = II.max - II.min
    else:
        div = II.max

    if isinstance(x, numbers.Real):
        return f'{x / div :.1%}'
    return '|'.join(_to_str(i, c) for i in x)


def check_devices():
    devices = device.input_devices()
    slices = mux.slice_all(devices.values(), DEVICE_SLICES)
    import pprint

    pprint.pprint(slices)
