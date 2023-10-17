import dataclasses as dc
import typing as t
from datetime import datetime
from pathlib import Path

import soundfile as sf
import threa

from recs.audio.legal_filename import legal_filename

from . import block, file_opener, times

TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'
NAME_JOINER = ' + '

now = datetime.now


@dc.dataclass
class ChannelWriter(threa.Runnable):
    opener: file_opener.FileOpener
    names: t.Sequence[str]
    path: Path
    times: times.Times[int]
    timestamp_format: str = TIMESTAMP_FORMAT

    blocks_written: int = 0
    files_written: int = 0
    samples_seen: int = 0

    _blocks: block.Blocks = dc.field(default_factory=block.Blocks)
    _sf: sf.SoundFile | None = None

    def __post_init__(self):
        super().__init__()
        self.start()

    def write(self, block: block.Block) -> None:
        if not self.running:
            return

        self.samples_seen += len(block)
        self._blocks.append(block)

        amp = self._blocks[-1].amplitude
        try:
            amp = sum(amp) / len(amp)
        except TypeError:
            pass

        if amp >= self.times.noise_floor_amplitude:
            self._record_on_not_silence()

        elif self._blocks.duration > self.times.stop_after_silence:
            self._close_on_silence()

    def stop(self) -> None:
        self.running.clear()

        if self._blocks:
            self._record(self._blocks)
            self._blocks.clear()

        if self._sf:
            self._sf.close()
            self._sf = None

        self.stopped.set()

    def _record_on_not_silence(self) -> None:
        if not self._sf:
            length = self.times.silence_before_start + len(self._blocks[-1])
            self._blocks.clip(length, from_start=True)

        self._record(self._blocks)
        self._blocks.clear()

    def _close_on_silence(self) -> None:
        removed = self._blocks.clip(self.times.silence_after_end, from_start=False)

        if self._sf:
            if removed:
                self._record(reversed(removed))

            self._sf.close()
            self._sf = None

    def _record(self, blocks: t.Iterable[block.Block]) -> None:
        for b in blocks:
            if not self._sf:
                self._sf = self._open_new_file()
                self.files_written += 1

            self._sf.write(b.block)
            self.blocks_written += 1

    def _open_new_file(self) -> sf.SoundFile:
        index = 0
        suffix = ''
        name = NAME_JOINER.join((*self.names, self._timestamp()))

        while True:
            p = self.path / legal_filename(name + suffix)
            try:
                return self.opener.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'

    def _timestamp(self) -> str:
        return now().strftime(self.timestamp_format)
