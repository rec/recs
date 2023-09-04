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
            self._not_silent()
        elif self._blocks.length > self.silence.before_stopping:
            self.close()

    def _not_silent(self):
        if not self._sf:
            self._blocks.clip_start(self.silence.at_start + len(self._blocks[-1]))
        self._record(self._blocks)
        self._blocks.clear()

    def close(self):
        removed = self._blocks.clip_end(self.silence.at_end)
        if self._sf:
            self._record(reversed(removed))
            self._sf.close()
            self._sf = None

    def _record(self, blocks):
        if not self._sf:
            self._sf or self.file_format.open(self._new_filename())
        for b in blocks:
            self._sf.write(b.block)

    def _new_filename(self) -> Path:
        return self.path / f'{self.name}-{ts()}'


def ts():
    return dt.now().strftime('%Y%m%d-%H%M%S')
