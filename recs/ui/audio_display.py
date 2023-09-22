import dataclasses as dc
import time
import typing as t

from rich.table import Table

from recs import field
from recs.audio import callback as ac
from recs.audio.block import Block
from recs.audio.device import InputDevice
from recs.ui.table import TableFormatter
from recs.util.counter import Accumulator, Counter


@dc.dataclass
class _ChannelCallback(ac.ChannelCallback):
    block_count: Counter = field(Counter)
    amplitude: Accumulator = field(Accumulator)
    rms: Accumulator = field(Accumulator)

    def callback(self, block):
        self.block_count()
        self.rms(block.rms)
        self.amplitude(block.amplitude)

    def rows(self):
        yield {
            'amplitude': self.amplitude.value,
            'amplitude_mean': self.amplitude.mean(),
            'channel': self.channel_name,
            'count': self.block_count.value,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }


@dc.dataclass
class _DeviceCallback(ac.DeviceCallback):
    Class = _ChannelCallback

    block_count: Counter = field(Counter)
    block_size: Accumulator = field(Accumulator)

    def callback(self, block, channel_name):
        self.block_count()
        assert block.channels <= 2, f'{len(block)=}, {block.channels=}'
        self.block_size(len(block))
        super().callback(block, channel_name)

    def rows(self):
        yield {
            'block': self.block_size.value,
            'count': self.block_count.value,
            'device': self.device.name,
        }
        for v in self.contents.values():
            yield from t.cast(_ChannelCallback, v).rows()


@dc.dataclass
class DevicesCallback(ac.DevicesCallback):
    block_count: Counter = field(Counter)
    start_time: float = field(time.time)

    Class = _DeviceCallback

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    def callback(self, block: Block, channel_name: str, device: InputDevice) -> None:
        self.block_count()
        super().callback(block, channel_name, device)

    def table(self) -> Table:
        return TABLE_FORMATTER(self.rows())

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'time': f'{self.elapsed_time:9.3f}',
            'count': self.block_count.value,
        }
        for v in self.contents.values():
            yield from t.cast(_DeviceCallback, v).rows()


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
