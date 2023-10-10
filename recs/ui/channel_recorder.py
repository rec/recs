import dataclasses as dc
import typing as t
from functools import cached_property

import numpy as np

from recs import field
from recs.audio import block, channel_writer, device
from recs.ui import counter, legal_filename, session


@dc.dataclass
class ChannelRecorder:
    name: str
    channels: slice
    device: device.InputDevice
    session: session.Session

    amplitude: counter.Accumulator = field(counter.Accumulator)
    block_count: int = 0
    rms: counter.Accumulator = field(counter.Accumulator)

    def callback(self, array: np.ndarray):
        b = block.Block(array[:, self.channels])
        self.block_count += 1
        self.rms(b.rms)
        self.amplitude(b.amplitude)
        if not self.session.recording.dry_run:  # type: ignore[attr-defined]
            self.channel_writer.write(b)

    def stop(self):
        if not self.session.recording.dry_run:
            self.channel_writer.close()

    @cached_property
    def channel_writer(self) -> channel_writer.ChannelWriter:
        channels = self.channels.stop - self.channels.start
        return channel_writer.ChannelWriter(
            name=legal_filename.legal_filename(f'{self.device.name}-{self.name}'),
            opener=self.session.opener(channels, self.device.samplerate),
            path=self.session.recording.path,  # type: ignore[attr-defined]
            runnable=self.session,
            times=self.session.times(self.device.samplerate),
        )

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {
            'amplitude': self.amplitude.value,
            'amplitude_mean': self.amplitude.mean(),
            'channel': self.name,
            'count': self.block_count,
            'rms': self.rms.value,
            'rms_mean': self.rms.mean(),
        }
