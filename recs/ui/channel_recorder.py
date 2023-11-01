import typing as t

import numpy as np

from recs import Cfg
from recs.audio import block, channel_writer, track
from recs.misc import counter, times


class ChannelRecorder:
    block_count: int = 0

    def __init__(self, cfg: Cfg, times: times.Times[int], track: track.Track) -> None:
        self.track = track
        self.writer = channel_writer.ChannelWriter(cfg, times, track)
        self.rms = counter.Accumulator()
        self.volume = counter.Accumulator()

        self.writer.start()
        self.stop = self.writer.stop

    def callback(self, array: np.ndarray) -> None:
        b = block.Block(array[:, self.track.slice])

        self.block_count += 1
        self.rms(b.rms)
        self.volume(b.volume)
        self.writer.write(b)

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'volume': self.volume.value,
            'volume_mean': self.volume.mean(),
            'channel': self.track.channels_name,
            'count': self.block_count,
            'total_size': self.writer.files_written.total_size,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }
