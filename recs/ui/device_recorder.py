from __future__ import annotations

import dataclasses as dc
import typing as t
from functools import cached_property

import numpy as np
import sounddevice as sd
from threa import Runnable

from recs.audio import auto_slice, device, times
from recs.audio.file_types import Format
from recs.ui.counter import Accumulator, Counter
from recs.ui.recorder import Recorder
from recs.ui.track import Track

if t.TYPE_CHECKING:
    from recs.ui.channel_recorder import ChannelRecorder


@dc.dataclass
class DeviceRecorder(Runnable):
    device: device.InputDevice
    recorder: Recorder

    block_count: Counter = dc.field(default_factory=Counter)
    block_size: Accumulator = dc.field(default_factory=Accumulator)

    def __post_init__(self) -> None:
        super().__init__()
        self.stopped.on_set.append(self.recorder.on_stopped)

    def __bool__(self) -> bool:
        return bool(self.channel_recorders)

    @cached_property
    def channel_recorders(self) -> tuple['ChannelRecorder', ...]:
        from recs.ui.channel_recorder import ChannelRecorder

        def recorder(channels_name: str, channels: slice) -> ChannelRecorder | None:
            return ChannelRecorder(
                channels=channels,
                names=[self.name, channels_name],
                samplerate=self.device.samplerate,
                recorder=self.recorder,
                times=self.times,
            )

        slices = auto_slice.auto_slice(self.device.channels)
        it = (recorder(k, v) for k, v in slices.items())
        return tuple(r for r in it if r is not None)

    @cached_property
    def input_stream(self) -> sd.InputStream:
        return self.device.input_stream(
            self.callback, self.recorder.stop, self.recorder.recs.dtype
        )

    @cached_property
    def name(self) -> str:
        name = self.device.name
        return self.recorder.aliases.inv.get(Track(name), name)

    @cached_property
    def times(self) -> times.Times[int]:
        return self.recorder.times(self.device.samplerate)

    @cached_property
    def total_run_time(self) -> float:
        return max(self.times.total_run_time, 0)

    def callback(self, array: np.ndarray) -> None:
        assert array.size

        fmt = self.recorder.recs.format
        if fmt == Format.mp3 and array.dtype == np.float32:
            # float32 crashes every time on my machine
            array = array.astype(np.float64)

        if array.dtype in (np.int8, np.int8):
            array = array.astype(np.int16)
            if array.dtype == np.uint8:
                array -= 0x80
            array *= 0x100

        self.block_count()
        size = array.shape[0]
        self.block_size(size)
        if self.total_run_time:
            if (delta := self.block_size.sum - self.total_run_time) >= 0:
                self.stop()
                if delta > 0:
                    if size <= delta:
                        return
                    array = array[slice(size - delta), :]

        for c in self.channel_recorders:
            c.callback(array)

        if not self.recorder.running:
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
        self.running.clear()
        self.input_stream.close()
        for c in self.channel_recorders:
            c.stop()
        self.stopped.set()
