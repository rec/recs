import dataclasses as dc
import typing as t

import numpy as np

from recs import RECS
from recs.audio import block, channel_writer, track

from ..misc import counter


@dc.dataclass
class ChannelRecorder:
    track: track.Track
    writer: channel_writer.ChannelWriter

    volume: counter.Accumulator = dc.field(default_factory=counter.Accumulator)
    block_count: int = 0
    rms: counter.Accumulator = dc.field(default_factory=counter.Accumulator)

    def callback(self, array: np.ndarray) -> None:
        b = block.Block(array[:, self.track.slice])

        self.block_count += 1
        self.rms(b.rms)
        self.volume(b.volume)
        if not RECS.dry_run:
            self.writer.write(b)

    def stop(self) -> None:
        if not RECS.dry_run:
            self.writer.stop()

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'volume': self.volume.value,
            'volume_mean': self.volume.mean(),
            'channel': self.track.channels_name,
            'count': self.block_count,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }
