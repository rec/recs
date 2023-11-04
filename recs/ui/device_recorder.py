from __future__ import annotations

import typing as t
from functools import cached_property, partial

import numpy as np
import sounddevice as sd
from threa import Runnable

from recs import Cfg
from recs.audio.file_types import SDTYPE, Format
from recs.audio.track import Track
from recs.misc.counter import Accumulator, Counter


class DeviceRecorder(Runnable):
    def __init__(self, cfg: Cfg, tracks: t.Sequence[Track]) -> None:
        from recs.ui.channel_recorder import ChannelRecorder

        super().__init__()
        self.cfg = cfg

        self.block_count = Counter()
        self.block_size = Accumulator()

        self.device = d = tracks[0].device
        self.name = self.cfg.aliases.display_name(d)
        self.times = self.cfg.times.scale(d.samplerate)

        make = partial(ChannelRecorder, cfg=cfg, times=self.times)
        self.channel_recorders = tuple(make(track=t) for t in tracks)

    def callback(self, array: np.ndarray) -> None:
        if self.cfg.format == Format.mp3 and array.dtype == np.float32:
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

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {'device': self.name}
        for v in self.channel_recorders:
            yield from v.rows()

    def stop(self) -> None:
        self.running.clear()
        for c in self.channel_recorders:
            c.stop()
        self.stopped.set()

    @property
    def file_count(self) -> int:
        return sum(c.file_count for c in self.channel_recorders)

    @property
    def file_size(self) -> int:
        return sum(c.file_size for c in self.channel_recorders)

    @property
    def recorded_time(self) -> float:
        return sum(c.recorded_time for c in self.channel_recorders)

    @cached_property
    def input_stream(self) -> sd.InputStream:
        return self.device.input_stream(
            callback=self.callback, dtype=self.cfg.sdtype or SDTYPE, stop=self.stop
        )
