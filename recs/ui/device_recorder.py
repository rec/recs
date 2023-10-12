import dataclasses as dc
import typing as t
from functools import cached_property

import numpy as np
import sounddevice as sd

from recs.audio import device, file_types, slicer, times
from recs.ui.channel_recorder import ChannelRecorder
from recs.ui.counter import Accumulator, Counter
from recs.ui.session import Session


@dc.dataclass
class DeviceRecorder:
    device: device.InputDevice
    session: Session
    block_count: Counter = dc.field(default_factory=Counter)
    block_size: Accumulator = dc.field(default_factory=Accumulator)

    def __bool__(self) -> bool:
        return bool(self.channel_recorders)

    @cached_property
    def channel_recorders(self) -> tuple[ChannelRecorder, ...]:
        def recorder(channels_name: str, channels: slice) -> ChannelRecorder | None:
            if not self.session.exclude_include(self.device, channels_name):
                return None

            return ChannelRecorder(
                channels=channels,
                name=(self.name, channels_name),
                samplerate=self.device.samplerate,
                session=self.session,
            )

        slices = slicer.slice_device(self.device, self.session.device_slices)
        it = (recorder(k, v) for k, v in slices.items())
        return tuple(r for r in it if r is not None)

    @cached_property
    def input_stream(self) -> sd.InputStream:
        return self.device.input_stream(
            self.callback, self.session.stop, self.session.dtype
        )

    @cached_property
    def name(self) -> str:
        name = self.device.name
        return self.session.aliases_inv.get((name, ''), [name])[0]

    @cached_property
    def times(self) -> times.Times[int]:
        return self.session.times(self.device.samplerate)

    @cached_property
    def total_run_time(self) -> int:
        return max(self.times.total_run_time, 0)

    def callback(self, array: np.ndarray) -> None:
        fmt = self.session.recording.format
        if fmt == file_types.Format.MP3 and array.dtype == np.float32:
            # Fix crash!
            array = array.astype(np.float64)

        self.block_count()
        size = array.shape[0]
        self.block_size(size)
        if self.total_run_time:
            if (delta := self.block_size.sum - self.total_run_time) >= 0:
                self.session.stop()
                if delta:
                    array = array[slice(size - delta), :]

        for c in self.channel_recorders:
            c.callback(array)

        if not self.session.running:
            self.stop()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'block': self.block_size.value,
            'count': self.block_count.value,
            'device': self.name,
        }
        for v in self.channel_recorders:
            yield from v.rows()

    def stop(self) -> None:
        for c in self.channel_recorders:
            c.stop()
