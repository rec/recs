import dataclasses as dc
import datetime.datetime as dt
from pathlib import Path

import soundfile as sf

from recs.audio.block import Block, Blocks
from recs.audio.file_format import AudioFileFormat
from recs.audio.silence import SilenceStrategy


@dc.dataclass
class FileWriter:
    file_format: AudioFileFormat
    name: str
    path: Path
    silence: SilenceStrategy[int]

    _blocks: Blocks = dc.field(default_factory=Blocks)
    _sf: sf.SoundFile | None = None

    def __call__(self, block: Block):
        self._blocks.append(block)
        if block.amplitude >= self.silence.noise_floor:
            self._block_not_silent()
        elif self._blocks.duration > self.silence.before_stopping:
            self._close()

    def _block_not_silent(self):
        if not self._sf:
            blocks = self._blocks
            length = self.silence.at_start + len(self._blocks[-1])
            blocks.clip(length, from_start=True)
        self._record(self._blocks)
        self._blocks.clear()

    def _close(self):
        blocks = self._blocks
        removed = blocks.clip(self.silence.at_end, from_start=False)
        if self._sf:
            self._record(reversed(removed))
            self._sf.close()
            self._sf = None

    def _record(self, blocks: Blocks):
        self._sf = self._sf or self.file_format.open(self._new_filename())
        for b in blocks:
            self._sf.write(b.block)

    def _new_filename(self) -> Path:
        return self.path / f'{self.name}-{ts()}'


def ts():
    return dt.now().strftime('%Y%m%d-%H%M%S')
