import dataclasses as dc
import typing as t
from functools import cached_property

import sounddevice as sd

from recs import Array, field
from recs.audio import device, slicer
from recs.ui.channel_recorder import ChannelRecorder
from recs.ui.counter import Accumulator, Counter
from recs.ui.session import Session


@dc.dataclass
class DeviceRecorder:
    device: device.InputDevice
    session: Session
    block_count: Counter = field(Counter)
    block_size: Accumulator = field(Accumulator)

    @cached_property
    def channel_recorders(self) -> tuple['ChannelRecorder', ...]:
        slices = slicer.slice_device(self.device, self.session.device_slices)
        it = ((k, v) for k, v in slices.items() if self.session.exc_inc(self.device, v))
        dr = self.device, self.session
        return tuple(ChannelRecorder(k, v, *dr) for k, v in it)

    @cached_property
    def input_stream(self) -> sd.InputStream:
        return self.device.input_stream(self.callback, self.session.stop)

    @cached_property
    def name(self) -> str:
        return self.session.device_names.get(self.device.name, self.device.name)

    def callback(self, array: Array) -> None:
        self.block_count()
        self.block_size(array.shape[0])

        for c in self.channel_recorders:
            c.callback(array)

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'block': self.block_size.value,
            'count': self.block_count.value,
            'device': self.name,
        }
        for v in self.channel_recorders:
            yield from v.rows()

    def stop(self):
        for c in self.channel_recorders:
            c.stop()
