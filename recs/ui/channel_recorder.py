import dataclasses as dc
import typing as t

import numpy as np

from recs import RECS
from recs.audio import channel_writer, file_opener
from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.audio.track import Track
from recs.misc.counter import Accumulator
from recs.misc.times import Times


@dc.dataclass
class ChannelRecorder:
    writer: ChannelWriter

    volume: Accumulator = dc.field(default_factory=Accumulator)
    block_count: int = 0
    rms: Accumulator = dc.field(default_factory=Accumulator)

    @property
    def track(self) -> Track:
        return self.writer.track

    def callback(self, array: np.ndarray) -> None:
        b = Block(array[:, self.track.slice])

        self.block_count += 1
        self.rms(b.rms)
        self.volume(b.volume)
        if not RECS.dry_run:
            self.writer.write(b)

    def stop(self) -> None:
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


def make(samplerate: int, track: Track, times: Times[int]) -> ChannelRecorder:
    opener = file_opener.FileOpener(channels=track.channel_count, samplerate=samplerate)
    writer = channel_writer.ChannelWriter(opener=opener, times=times, track=track)
    return ChannelRecorder(writer=writer)
