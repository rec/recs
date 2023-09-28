import dataclasses as dc
import time
import typing as t
from abc import ABC, abstractmethod
from functools import cached_property
from threading import Lock

from rich.table import Table

from recs import cli, field
from recs.audio.mux import AudioUpdate

from .counter import Accumulator, Counter
from .table import TableFormatter


class HasRows(ABC):
    @abstractmethod
    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        pass

    @abstractmethod
    def callback(self, u: AudioUpdate) -> None:
        pass


class Maker(HasRows, ABC):
    def __init__(self) -> None:
        self._lock = Lock()
        self.contents: t.Dict[str, HasRows] = {}

    def __post_init__(self):
        Maker.__init__(self)

    @cached_property
    def start_time(self):
        return time.time()

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    key_name: str

    @abstractmethod
    def make(self, u: AudioUpdate) -> HasRows:
        pass

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        for v in self.contents.values():
            yield from v.rows()

    def callback(self, u: AudioUpdate) -> None:
        name = getattr(u, self.key_name)

        with self._lock:
            try:
                has_rows = self.contents[name]
            except KeyError:
                self.contents[name] = has_rows = self.make(u)
        has_rows.callback(u)


class DeviceCallback(Maker):
    """This class gets callbacks from blocks from a single device"""

    key_name = 'channel_name'


class DevicesCallback(Maker):
    """This class gets callbacks from all blocks from all devices"""

    key_name = 'device_name'


@dc.dataclass
class Recorder(DevicesCallback):
    recording: cli.Recording
    block_count: Counter = field(Counter)
    start_time: float = field(time.time)

    def make(self, u: AudioUpdate) -> HasRows:
        return _DeviceCallback(u)

    @property
    def elapsed_time(self):
        return time.time() - self.start_time

    def callback(self, u: AudioUpdate) -> None:
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
class _DeviceCallback(DeviceCallback):
    update: AudioUpdate
    block_count: Counter = field(Counter)
    block_size: Accumulator = field(Accumulator)
    device_name: str = ''

    def make(self, u: AudioUpdate) -> HasRows:
        return _ChannelCallback(u)

    def callback(self, u: AudioUpdate):
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
class _ChannelCallback(HasRows):
    update: AudioUpdate
    block_count: Counter = field(Counter)
    amplitude: Accumulator = field(Accumulator)
    rms: Accumulator = field(Accumulator)

    channel_name: str = ''
    channel_count: int = 0

    def callback(self, u: AudioUpdate):
        self.block_count()
        self.rms(u.block.rms)
        self.amplitude(u.block.amplitude)
        if not self.channel_count:
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
