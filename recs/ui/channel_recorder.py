import typing as t

import numpy as np

from recs import Cfg
from recs.audio import block, channel_writer, track
from recs.base import times
from recs.misc import counter


class ChannelRecorder:
    block_count: int = 0
    block_size: int = 0

    def __init__(self, cfg: Cfg, times: times.Times[int], track: track.Track) -> None:
        self.track = track
        self.writer = channel_writer.ChannelWriter(cfg, times, track)
        self.volume = counter.MovingBlock(times.moving_average_time)

        self.writer.start()
        self.stop = self.writer.stop

    def callback(self, array: np.ndarray, time: float) -> None:
        b = block.Block(array[:, self.track.slice])
        self.writer.write(b, time)

        self.block_size = len(b)
        self.block_count += 1
        self.volume(b)

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
            'volume': self.volume.mean(),
        }
