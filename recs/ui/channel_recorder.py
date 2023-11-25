import typing as t

import numpy as np

from recs.audio import block, channel_writer
from recs.base.message import ChannelMessage
from recs.cfg import Cfg, Track, time_settings
from recs.misc import counter


class ChannelRecorder:
    def __init__(
        self, cfg: Cfg, times: time_settings.TimeSettings[int], track: Track
    ) -> None:
        self.track = track
        self.writer = channel_writer.ChannelWriter(cfg, times, track)
        self.volume = counter.MovingBlock(times.moving_average_time)

        self.writer.start()
        self.stop = self.writer.stop

    def callback(self, array: np.ndarray, time: float) -> ChannelMessage:
        b = block.Block(array[:, self.track.slice])
        self.volume(b)

        s = self.writer.state()
        self.writer.write(b, time)
        t = self.writer.state()

        return ChannelMessage(
            t.file_count - s.file_count,
            t.file_size - s.file_size,
            t.is_active,
            t.recorded - s.recorded,
            tuple(self.volume.mean()),
        )

    @property
    def file_count(self) -> int:
        return len(self.writer.files_written)

    @property
    def file_size(self) -> int:
        return self.writer.files_written.total_size

    @property
    def recorded_time(self) -> float:
        return self.writer.frames_written / self.track.device.samplerate

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        m = self.volume.mean()
        volume = len(m) and sum(m) / len(m)
        yield {
            'channel': self.track.channels_name,
            'on': self.writer.active,
            'recorded': self.recorded_time,
            'file_size': self.file_size,
            'file_count': self.file_count,
            'volume': volume,
        }
