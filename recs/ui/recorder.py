import contextlib
import dataclasses as dc
import time
import typing as t
from functools import cached_property

import sounddevice as sd
from rich.table import Table

from recs import Array, field
from recs.audio import block, channel_writer, device, slicer

from .counter import Accumulator, Counter
from .legal_filename import legal_filename
from .session import Session
from .table import TableFormatter


class Recorder:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.start_time = time.time()
        devices = session.devices.values()
        self.devices = tuple(DeviceCallback(d, session) for d in devices)

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    def table(self) -> Table:
        return TABLE_FORMATTER(self.rows())

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {'time': f'{self.elapsed_time:9.3f}'}
        for v in self.devices:
            yield from v.rows()

    @contextlib.contextmanager
    def context(self):
        try:
            with contextlib.ExitStack() as stack:
                for d in self.devices:
                    stack.enter_context(d.input_stream)
                yield
        finally:
            self.stop()

    def stop(self):
        for d in self.devices:
            d.stop()


@dc.dataclass
class DeviceCallback:
    device: device.InputDevice
    session: Session
    block_count: Counter = field(Counter)
    block_size: Accumulator = field(Accumulator)

    @cached_property
    def channels(self) -> tuple['ChannelCallback', ...]:
        slices = slicer.slice_device(self.device, self.session.device_slices)
        dr = self.device, self.session
        return tuple(ChannelCallback(k, v, *dr) for k, v in slices.items())

    @cached_property
    def input_stream(self) -> sd.InputStream:
        return self.device.input_stream(self.callback, self.session.stop)

    def callback(self, array: Array) -> None:
        self.block_count()
        self.block_size(array.shape[0])

        for c in self.channels:
            c.callback(array)

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'block': self.block_size.value,
            'count': self.block_count.value,
            'device': self.device.name,
        }
        for v in self.channels:
            yield from v.rows()

    def stop(self):
        for c in self.channels:
            c.stop()


@dc.dataclass
class ChannelCallback:
    name: str
    channels: slice
    device: device.InputDevice
    session: Session

    block_count: Counter = field(Counter)
    amplitude: Accumulator = field(Accumulator)
    rms: Accumulator = field(Accumulator)

    def callback(self, array: Array):
        b = block.Block(array[:, self.channels])
        self.block_count()
        self.rms(b.rms)
        self.amplitude(b.amplitude)
        if not self.session.recording.dry_run:  # type: ignore[attr-defined]
            self.channel_writer.write(b)

    def stop(self):
        if not self.session.recording.dry_run:
            self.channel_writer.close()

    @cached_property
    def channel_writer(self) -> channel_writer.ChannelWriter:
        channels = self.channels.stop - self.channels.start
        return channel_writer.ChannelWriter(
            opener=self.session.opener(channels, self.device.samplerate),
            name=legal_filename(f'{self.device.name}-{self.name}'),
            path=self.session.recording.path,  # type: ignore[attr-defined]
            silence=self.session.silence(self.device.samplerate),
        )

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'amplitude': self.amplitude.value,
            'amplitude_mean': self.amplitude.mean(),
            'channel': self.name,
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
