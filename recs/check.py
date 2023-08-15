from . import device, mux
from .block import Block
from collections import defaultdict
from functools import cached_property
import dataclasses as dc
import math
import time
import typing as t

from rich.live import Live
from rich.table import Table

DEVICE_SLICES = {'FLOW': mux.auto_slice(8) | {'Main': slice(8, 10)}}


def field(default_factory: t.Callable[[], t.Any], **ka):
    return dc.field(default_factory=default_factory, **ka)


class Counter:
    value = 0

    @cached_property
    def counter(self):
        return self.itertools.count()

    def increment(self) -> int:
        self.value = v = next(self.counter)
        return v


@dc.dataclass
class Accumulator:
    count: int = 0
    sum: float = 0
    square_sum: float = 0
    last: float = 0

    def accum(self, x: float):
        self.last = x
        self.count += 1
        self.sum += x
        self.square_sum += x * x

    def mean(self) -> float:
        return self.count and self.sum / self.count

    def stdev(self) -> float:
        return self.count and math.sqrt(self.square_sum / self.count)


@dc.dataclass
class Channel:
    block_count: Counter = field(Counter)
    amplitude: Accumulator = field(Accumulator)
    rms: Accumulator = field(Accumulator)

    def __call__(self, block):
        self.rms(block.rms)
        self.amplitude(block.amplitude)

    def rows(self, channel):
        yield {
            'channel': channel,
            'count': self.block_count.value,
            'amplitude': self.amplitude.value,
            'amplitude_mean': self.amplitude.mean(),
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }


@dc.dataclass
class Device:
    block_count: Counter = field(Counter)
    block_size: Accumulator = field(Accumulator)
    channels: dict[str, Channel] = field(lambda: defaultdict(Channel))

    def __call__(self, frame, channel_name):
        block = Block(frame)
        self.block_size.accum(len(block))
        self.channels[channel_name](block)

    def rows(self, name):
        yield {
            'device': name,
            'count': self.block_count.value,
            'block_size': self.block_size.last,
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
        self.block_count.increment()
        self.devices[device.name](frame, channel_name)

    def table(self):
        t = Table(*COLUMNS)
        for row in self.rows():
            [str(row.get(c, '')) for c in COLUMNS]

        return t

    def rows(self):
        yield {'time': round(self.elapsed_time, 2)}
        for k, v in self.devices.items():
            yield from v.rows(k)


COLUMNS = (
    'time',
    'device',
    'channel',
    'count',
    'block_size',
    'rms',
    'rms_mean',
    'amplitude',
    'amplitude_mean',
)

"""

global:
  time elapsed: in seconds
  block count

per device:
  block count
  last block size
  sample rate

per slice:
  block count

max, min, mean for

amplitude
DC offset
RMS

"""


def check_old():
    devices = device.input_devices()
    slices = mux.slice_all(devices.values(), DEVICE_SLICES)
    import pprint

    pprint.pprint(slices)


def check():
    import random

    def generate_table() -> Table:
        """Make a new table."""
        table = Table()
        table.add_column("ID")
        table.add_column("Value")
        table.add_column("Status")

        for row in range(random.randint(2, 6)):
            value = random.random() * 100
            table.add_row(
                f"{row}",
                f"{value:3.2f}",
                "[red]ERROR" if value < 50 else "[green]SUCCESS",
            )
        return table

    with Live(generate_table(), refresh_per_second=4) as live:
        for _ in range(40):
            time.sleep(0.4)
            live.update(generate_table())
