import dataclasses as dc
import typing as t
from functools import cached_property

import numpy as np

from recs import RECS
from recs.audio import block, channel_writer

from . import counter, device_recorder


@dc.dataclass
class ChannelRecorder:
    channels: slice
    names: t.Sequence[str]
    samplerate: int
    recorder: device_recorder.DeviceRecorder

    volume: counter.Accumulator = dc.field(default_factory=counter.Accumulator)
    block_count: int = 0
    rms: counter.Accumulator = dc.field(default_factory=counter.Accumulator)

    def callback(self, array: np.ndarray) -> None:
        b = block.Block(array[:, self.channels])

        self.block_count += 1
        self.rms(b.rms)
        self.volume(b.volume)
        if not RECS.dry_run:
            self.channel_writer.write(b)

    def stop(self) -> None:
        if not RECS.dry_run:
            self.channel_writer.stop()

    @cached_property
    def channel_writer(self) -> channel_writer.ChannelWriter:
        channels = self.channels.stop - self.channels.start

        return channel_writer.ChannelWriter(
            names=self.names,
            opener=self.recorder.opener(channels),
            path=RECS.path,
            times=self.recorder.times,
        )

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'volume': self.volume.value,
            'volume_mean': self.volume.mean(),
            'channel': self.names[1],  # Really?
            'count': self.block_count,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }
