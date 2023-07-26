from . import Array, block
from functools import cached_property
from pathlib import Path
import dataclasses as dc
import datetime.datetime as dt
import soundfile as sf


@dc.dataclass
class SilenceStrategy:
    at_start: int
    at_end: int
    before_splitting: int
    noise_floor_db: float = 70
    sample_range: int = 0x1_0000_0000

    @cached_property
    def noise_floor(self):
        ratio = 10 ** (self.noise_floor_db / 10)
        return self.sample_range // ratio


@dc.dataclass
class ChannelListener:
    channel_slice: slice
    name: str
    path: Path
    samplerate: int
    silence: SilenceStrategy

    file_suffix: str = ".flac"
    subtype: str = "PCM_24"

    _blocks: block.Blocks = dc.field(default_factory=block.Blocks)
    _sf: sf.SoundFile | None = None

    def __callback__(self, frames: Array):
        new_block = block.Block(frames[:, self.channel_slice])
        self._blocks.append(new_block)

        if new_block.amplitude >= self.silence.noise_floor:
            if not self._sf:
                self._blocks.clip_to_length(self.silence.at_start + len(new_block))
            self._record()

        elif self._blocks.length > self.silence.before_splitting:
            self.close()

    def _record(self):
        self._sf = self._sf or sf.SoundFile(
            self._new_filename(),
            channels=len(self.channel_slice),
            mode="x",
            samplerate=self.samplerate,
            subtype=self.subtype,
        )
        for b in self._blocks:
            self._sf.write(b.block)
        self._blocks.clear()

    def close(self):
        if self._sf:
            blocks = self._blocks[: self.silence.at_end]
            self._blocks = self._blocks[self.silence.at_end :]
            self.record(blocks)
            self._sf.close()
            self._sf = None

    def _new_filename(self):
        filename = str(self.path / f"{self.name}-{ts()}{self.file_suffix}")
        print("Creating", filename)
        return filename


def ts():
    return dt.now().strftime("%Y%m%d-%H%M%S")


@dc.dataclass
class Universe:
    pass
    # device: Device


"""
"""
