from __future__ import annotations

import typing as t
from functools import cached_property, partial

import numpy as np
import sounddevice as sd
from threa import Runnable

from recs.base import times
from recs.base.types import SDTYPE, Active, Format
from recs.cfg import Cfg, Track
from recs.misc.counter import Accumulator, Counter

OFFLINE_TIME = 1


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
        self.timestamp = times.time()

    def callback(self, array: np.ndarray, time: float) -> None:
        self.timestamp = time

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
            c.callback(array, time)

    def active(self) -> Active:
        dt = self.timestamp and times.time() - self.timestamp
        return Active.offline if dt > OFFLINE_TIME else Active.active

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        active = self.active()
        yield {'on': active}
        yield {'device': self.name}
        for v in self.channel_recorders:
            for r in v.rows():
                if active == Active.offline:
                    yield r | {'on': active}
                else:
                    yield r

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
