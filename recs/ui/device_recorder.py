import typing as t
from functools import cached_property, partial

import numpy as np
from threa import Runnable, ThreadQueue

from recs.base import message, times
from recs.base.types import Active, Format, Stop
from recs.cfg import Cfg, Track

from .channel_recorder import ChannelRecorder

OFFLINE_TIME = 1


class DeviceRecorder(Runnable):
    elapsed_samples: int = 0
    file_count: int = 0
    file_size: int = 0
    recorded_time: float = 0

    def __init__(
        self,
        cfg: Cfg,
        tracks: t.Sequence[Track],
        stop_all: Stop,
        callback: t.Callable[[message.DeviceMessages], None],
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.stop_all = stop_all

        self.callback = callback
        self.device = d = tracks[0].device
        self.name = self.cfg.aliases.display_name(d)
        self.times = self.cfg.times.scale(d.samplerate)

        make = partial(ChannelRecorder, cfg=cfg, times=self.times)

        self.channel_recorders = tuple(make(track=t) for t in tracks)
        self.timestamp = times.time()
        self.queue = ThreadQueue(callback=self.audio_callback)

    def audio_callback(self, array: np.ndarray) -> None:
        self.timestamp = times.time()

        if self.cfg.format == Format.mp3 and array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            array = array.astype(np.float64)

        def msg(cr: ChannelRecorder) -> tuple[str, message.ChannelMessage]:
            return cr.track.channels_name, cr.callback(array, self.timestamp)

        msgs = dict(msg(c) for c in self.channel_recorders)

        self.elapsed_samples += len(array)
        if (t := self.times.total_run_time) and self.elapsed_samples >= t:
            self.stop()

        self.callback(msgs)

    def active(self) -> Active:
        # TODO: this does work but we should probably bypass this
        dt = times.time() - self.timestamp
        return Active.offline if dt > OFFLINE_TIME else Active.active

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        active = self.active()
        yield {'device': self.name, 'on': active}
        for v in self.channel_recorders:
            for r in v.rows():
                if active == Active.offline:
                    yield r | {'on': active}
                else:
                    yield r

    def start(self) -> None:
        super().start()
        self.queue.start()

    def stop(self) -> None:
        self.running.clear()
        self.queue.stop()
        for c in self.channel_recorders:
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
