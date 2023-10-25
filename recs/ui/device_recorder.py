from __future__ import annotations

import typing as t
from functools import cached_property

import numpy as np
import sounddevice as sd
from threa import Runnable

from recs import RECS
from recs.audio import device, file_opener
from recs.audio.file_types import Format

from .counter import Accumulator, Counter
from .recorder import Recorder
from .track import Track

if t.TYPE_CHECKING:
    from .ui.channel_recorder import ChannelRecorder


class DeviceRecorder(Runnable):
    def __init__(
        self, d: device.InputDevice, recorder: Recorder, tracks: t.Sequence[Track]
    ) -> None:
        super().__init__()

        self.device = d
        self.recorder = recorder
        self.stopped.on_set.append(self.recorder.on_stopped)
        self.block_count = Counter()
        self.block_size = Accumulator()
        self.times = self.recorder.times(self.device.samplerate)
        self.name = self.recorder.aliases.inv.get(Track(d), d.name)

        from recs.ui.channel_recorder import ChannelRecorder

        def channel_recorder(track: Track) -> ChannelRecorder:
            return ChannelRecorder(
                channels=track.slice,
                names=[self.name, track.channels_name],
                samplerate=self.device.samplerate,
                recorder=self,
            )

        self.channel_recorders = tuple(channel_recorder(t) for t in tracks)

    def callback(self, array: np.ndarray) -> None:
        if RECS.format == Format.mp3 and array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            array = array.astype(np.float64)

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
        for c in self.channel_recorders:
            c.stop()
        self.stopped.set()

    @cached_property
    def input_stream(self) -> sd.InputStream:
        return self.device.input_stream(
            callback=self.callback,
            dtype=self.recorder.dtype,
            stop=self.recorder.stop,
        )

    def opener(self, channels: int) -> file_opener.FileOpener:
        return file_opener.FileOpener(
            channels=channels,
            format=RECS.format,
            samplerate=self.device.samplerate,
            subtype=self.recorder.subtype,
        )
