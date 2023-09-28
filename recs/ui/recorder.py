import dataclasses as dc
import time
import typing as t

from rich.table import Table

from recs import cli, field
from recs.audio import callback, mux
from recs.ui.counter import Accumulator, Counter
from recs.ui.table import TableFormatter


@dc.dataclass
class Recorder(callback.DevicesCallback):
    recording: cli.Recording
    block_count: Counter = field(Counter)
    start_time: float = field(time.time)

    def make(self):
        return _DeviceCallback()

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    def callback(self, u: mux.AudioUpdate) -> None:
        self.block_count()
        super().callback(u)

    def table(self) -> Table:
        return TABLE_FORMATTER(self.rows())

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'time': f'{self.elapsed_time:9.3f}',
            'count': self.block_count.value,
        }
        yield from super().rows()


@dc.dataclass
class _DeviceCallback(callback.DeviceCallback):
    block_count: Counter = field(Counter)
    block_size: Accumulator = field(Accumulator)
    device_name: str = ''

    def make(self):
        return _ChannelCallback()

    def callback(self, u: mux.AudioUpdate):
        self.block_count()
        assert u.block.channels <= 2, f'{len(u.block)=}, {u.block.channels=}'
        self.block_size(len(u.block))
        self.device_name = u.device.name
        super().callback(u)

    def rows(self):
        yield {
            'block': self.block_size.value,
            'count': self.block_count.value,
            'device': self.device_name,
        }
        yield from super().rows()


@dc.dataclass
class _ChannelCallback(callback.HasRows):
    block_count: Counter = field(Counter)
    amplitude: Accumulator = field(Accumulator)
    rms: Accumulator = field(Accumulator)

    channel_name: str = ''

    def callback(self, u: mux.AudioUpdate):
        self.block_count()
        self.rms(u.block.rms)
        self.amplitude(u.block.amplitude)
        self.channel_name = u.channel_name

    def rows(self):
        yield {
            'amplitude': self.amplitude.value,
            'amplitude_mean': self.amplitude.mean(),
            'channel': self.channel_name,
            'count': self.block_count.value,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }


def _to_str(x) -> str:
    if isinstance(x, str):
        return x

    global RED, GREEN, BLUE
    RED = (RED + 1) % 256
    GREEN = (GREEN + 1) % 256
    BLUE = (BLUE + 1) % 256
    return f'[rgb({RED},{GREEN},{BLUE})]{x:>7,}'


RED = 256 // 3
GREEN = 512 // 3
BLUE = 0


TABLE_FORMATTER = TableFormatter(
    time=None,
    device=None,
    channel=None,
    count=_to_str,
    block=_to_str,
    rms=None,
    rms_mean=None,
    amplitude=None,
    amplitude_mean=None,
)
