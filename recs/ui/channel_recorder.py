import dataclasses as dc
import typing as t
from functools import cached_property

import numpy as np

from recs.audio import block, channel_writer
from recs.ui import counter, session


@dc.dataclass
class ChannelRecorder:
    channels: slice
    name: t.Sequence[str]
    samplerate: int
    session: session.Session

    amplitude: counter.Accumulator = dc.field(default_factory=counter.Accumulator)
    block_count: int = 0
    rms: counter.Accumulator = dc.field(default_factory=counter.Accumulator)

    def callback(self, array: np.ndarray) -> None:
        b = block.Block(array[:, self.channels])
        self.block_count += 1
        self.rms(b.rms)
        self.amplitude(b.amplitude)
        if not self.session.recording.dry_run:  # type: ignore[attr-defined]
            self.channel_writer.write(b)

    def stop(self) -> None:
        if not self.session.recording.dry_run:  # type: ignore[attr-defined]
            self.channel_writer.close()

    @cached_property
    def channel_writer(self) -> channel_writer.ChannelWriter:
        channels = self.channels.stop - self.channels.start
        rec = self.session.recording

        return channel_writer.ChannelWriter(
            name=self.name,
            opener=self.session.opener(channels, self.samplerate),
            path=rec.path,  # type: ignore[attr-defined]
            runnable=self.session,
            times=self.session.times(self.samplerate),
            timestamp_format=rec.timestamp_format,  # type: ignore[attr-defined]
        )

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'amplitude': self.amplitude.value,
            'amplitude_mean': self.amplitude.mean(),
            'channel': self.name[1],
            'count': self.block_count,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }
