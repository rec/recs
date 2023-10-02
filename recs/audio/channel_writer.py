import dataclasses as dc
from datetime import datetime as dt
from pathlib import Path

import soundfile as sf

from . import block, file_opener, silence


@dc.dataclass
class ChannelWriter:
    opener: file_opener.FileOpener
    name: str
    path: Path
    silence: silence.SilenceStrategy[int]

    block_count: int = 0
    file_count: int = 0

    _blocks: block.Blocks = dc.field(default_factory=block.Blocks)
    _current_file: Path = Path()
    _sf: sf.SoundFile | None = None

    @property
    def is_recording(self) -> bool:
        return bool(self._sf)

    @property
    def current_file(self) -> Path:
        return self._current_file

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        try:
            self.close()
        except Exception:
            if type is not None:
                raise

    def write(self, block: block.Block):
        self._blocks.append(block)

        amp = self._blocks[-1].amplitude
        try:
            amp = sum(amp) / len(amp)
        except TypeError:
            pass

        if amp >= self.silence.noise_floor_amplitude:
            self._record_on_not_silence()

        elif self._blocks.duration > self.silence.stop_after:
            self._close_on_silence()

    def close(self):
        if self._sf:
            self._record(self._blocks)
            self._sf.close()
            self._sf = None

        self._blocks.clear()

    def _record_on_not_silence(self):
        if not self._sf:
            length = self.silence.before_start + len(self._blocks[-1])
            self._blocks.clip(length, from_start=True)

        self._record(self._blocks)
        self._blocks.clear()

    def _close_on_silence(self):
        removed = self._blocks.clip(self.silence.after_end, from_start=False)

        if self._sf:
            if removed:
                self._record(reversed(removed))
            self._sf.close()
            self._sf = None

    def _record(self, blocks: block.Blocks):
        if not self._sf:
            self._new_file()
            self._sf = self.opener.open(self.current_file, 'w')
            self.file_count += 1

        for b in blocks:
            self._sf.write(b.block)
            self.block_count += 1

    def _new_file(self):
        istr = ''
        index = 0
        while True:
            p = self.path / f'{self.name}-{ts()}{istr}'
            self._current_file = p.with_suffix(self.opener.suffix)
            if not self._current_file.exists():
                return
            index += 1
            istr = f'_{index}'


def ts():
    return dt.now().strftime('%Y%m%d-%H%M%S')
