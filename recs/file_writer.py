import dataclasses as dc
import datetime.datetime as dt
from pathlib import Path

import soundfile as sf

from .block import Block, Blocks
from .silence import SilenceStrategy


@dc.dataclass
class FileFormat:
    channels: int
    samplerate: int
    subtype: str = 'PCM_24'

    def open(self, filename: Path) -> sf.SoundFile:
        return sf.SoundFile(filename, **dc.asdict(self))


@dc.dataclass
class FileWriter:
    file_format: FileFormat
    name: str
    path: Path
    silence: SilenceStrategy

    file_suffix: str = '.flac'

    _blocks: Blocks = dc.field(default_factory=Blocks)
    _sf: sf.SoundFile | None = None

    def __call__(self, block: Block):
        self._blocks.append(block)

        if block.amplitude >= self.silence.noise_floor:
            if not self._sf:
                self._blocks.clip_to_length(self.silence.at_start + len(block))
            self._record()

        elif self._blocks.length > self.silence.before_splitting:
            self.close()

    def _record(self):
        self._sf = self._sf or self.file_format.open(self._new_filename())
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
        filename = str(self.path / f'{self.name}-{ts()}{self.file_suffix}')
        print('Creating', filename)
        return filename


def ts():
    return dt.now().strftime('%Y%m%d-%H%M%S')


@dc.dataclass
class Universe:
    pass
    # device: Device


"""
"""
