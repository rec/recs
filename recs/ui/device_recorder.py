import typing as t
from functools import cached_property, partial

import numpy as np
from threa import Runnable, ThreadQueue

from recs.audio.channel_writer import ChannelWriter
from recs.base import state, times
from recs.base.types import Active, Format, Stop
from recs.cfg import Cfg, Track

OFFLINE_TIME = 1


class DeviceRecorder(Runnable):
    elapsed_samples: int = 0

    def __init__(
        self,
        cfg: Cfg,
        tracks: t.Sequence[Track],
        stop_all: Stop,
        callback: t.Callable[[state.RecorderState], None],
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.stop_all = stop_all

        self.callback = callback
        self.device = d = tracks[0].device
        self.name = self.cfg.aliases.display_name(d)
        self.times = self.cfg.times.scale(d.samplerate)

        make = partial(ChannelWriter, cfg=cfg, times=self.times)

        self.channel_writers = tuple(make(track=t) for t in tracks)
        self.timestamp = times.time()
        self.queue = ThreadQueue(callback=self.audio_callback)

    def audio_callback(self, array: np.ndarray) -> None:
        self.timestamp = times.time()

        if self.cfg.format == Format.mp3 and array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            array = array.astype(np.float64)

        def msg(cr: ChannelWriter) -> tuple[str, state.ChannelState]:
            return cr.track.name, cr.callback(array, self.timestamp)

        msgs = dict(msg(c) for c in self.channel_writers)

        self.elapsed_samples += len(array)
        if (t := self.times.total_run_time) and self.elapsed_samples >= t:
            self.stop()

        self.callback({self.device.name: msgs})

    def active(self) -> Active:
        # TODO: this does work but we should probably bypass this
        dt = times.time() - self.timestamp
        return Active.offline if dt > OFFLINE_TIME else Active.active

    def start(self) -> None:
        super().start()
        self.queue.start()

    def stop(self) -> None:
        self.running.clear()
        self.queue.stop()
        for c in self.channel_writers:
            c.stop()
        self.stopped.set()

    def __enter__(self):
        if self.input_stream:
            self.input_stream.__enter__()

    def __exit__(self, *a) -> None:
        if input_stream := self.__dict__.get('input_stream'):
            return input_stream.__exit__(*a)

    @cached_property
    def input_stream(self) -> t.Iterator[None] | None:
        return self.device.input_stream(
            callback=self.queue.queue.put, dtype=self.cfg.sdtype, stop_all=self.stop_all
        )
