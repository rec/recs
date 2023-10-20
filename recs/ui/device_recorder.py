from __future__ import annotations

import typing as t
from functools import cached_property

import numpy as np
import sounddevice as sd
from threa import Runnable

from recs import RECS
from recs.audio import auto_slice, device, file_opener
from recs.audio.file_types import Format
from recs.ui.counter import Accumulator, Counter
from recs.ui.recorder import Recorder
from recs.ui.track import Track

if t.TYPE_CHECKING:
    from recs.ui.channel_recorder import ChannelRecorder


class DeviceRecorder(Runnable):
    def __init__(self, d: device.InputDevice, recorder: Recorder) -> None:
        super().__init__()
        self.device = d
        self.recorder = recorder
        self.stopped.on_set.append(self.recorder.on_stopped)
        self.block_count = Counter()
        self.block_size = Accumulator()
        self.times = self.recorder.times(self.device.samplerate)
        self.name = self.recorder.aliases.inv.get(Track(d.name), d.name)

    def __bool__(self) -> bool:
        return bool(self.channel_recorders)

    @cached_property
    def channel_recorders(self) -> tuple['ChannelRecorder', ...]:
        from recs.ui.channel_recorder import ChannelRecorder

        def recorder(channels_name: str, channels: slice) -> ChannelRecorder:
            return ChannelRecorder(
                channels=channels,
                names=[self.name, channels_name],
                samplerate=self.device.samplerate,
                recorder=self,
            )

        slices = auto_slice.auto_slice(self.device.channels)
        it = (recorder(k, v) for k, v in slices.items())
        return tuple(r for r in it if r is not None)

    @cached_property
    def input_stream(self) -> sd.InputStream:
        return self.device.input_stream(self.callback, self.recorder.stop, RECS.dtype)

    def callback(self, array: np.ndarray) -> None:
        if RECS.format == Format.mp3 and array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            array = array.astype(np.float64)

        if array.dtype in (np.int8, np.int8):
            array = array.astype(np.int16)
            if array.dtype == np.uint8:
                array -= 0x80
            array *= 0x100

        self.block_count()
        self.block_size(array.shape[0])

        if (t := self.times.total_run_time) and (extra := self.block_size.sum - t) >= 0:
            self.stop()
            if array.shape[0] <= extra:
                return
            array = array[slice(extra), :]

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

    def opener(self, channels: int) -> file_opener.FileOpener:
        return file_opener.FileOpener(
            channels=channels,
            format=RECS.format,
            samplerate=self.device.samplerate,
            subtype=RECS.subtype,
        )
