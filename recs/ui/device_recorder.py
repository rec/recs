from __future__ import annotations

import typing as t
from functools import cached_property

import numpy as np
import sounddevice as sd
from threa import Runnable

from recs import RECS
from recs.audio import device
from recs.audio.file_types import Format
from recs.audio.track import Track
from recs.misc.counter import Accumulator, Counter

from .recorder import Recorder

if t.TYPE_CHECKING:
    pass


class DeviceRecorder(Runnable):
    def __init__(
        self, d: device.InputDevice, recorder: Recorder, tracks: t.Sequence[Track]
    ) -> None:
        super().__init__()
        self.stopped.on_set.append(recorder.on_stopped)

        self.block_count = Counter()
        self.block_size = Accumulator()
        self.device = d
        self.name = RECS.aliases.display_name(d)
        self.recorder = recorder
        self.times = RECS.times.scale(d.samplerate)

        from recs.ui import channel_recorder

        def make(track: Track) -> channel_recorder.ChannelRecorder:
            return channel_recorder.make(
                samplerate=d.samplerate,
                track=track,
                times=self.times,
            )

        self.channel_recorders = tuple(make(t) for t in tracks)

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
        return self.device.input_stream(callback=self.callback, stop=self.stop)
