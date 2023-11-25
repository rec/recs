import typing as t

import numpy as np

from recs.audio import block, channel_writer
from recs.base.state import ChannelState
from recs.cfg import Cfg, Track, time_settings


class ChannelRecorder:
    def __init__(
        self, cfg: Cfg, times: time_settings.TimeSettings[int], track: Track
    ) -> None:
        self.track = track
        self.writer = channel_writer.ChannelWriter(cfg, times, track)

        self.writer.start()
        self.stop = self.writer.stop

    def callback(self, array: np.ndarray, time: float) -> ChannelState:
        saved_state = self.writer.state()

        b = block.Block(array[:, self.track.slice])
        self.writer.write(b, time)

        return self.writer.state() - saved_state

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
        yield {
            'channel': self.track.channels_name,
            'on': self.writer.active,
            'recorded': self.recorded_time,
            'file_size': self.file_size,
            'file_count': self.file_count,
            'volume': self.writer.volume,
        }
