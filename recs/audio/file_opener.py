import dataclasses as dc
import typing as t
from pathlib import Path

import soundfile as sf

from .file_types import Format, Subtype
from .valid_subtypes import is_valid


@dc.dataclass(frozen=True)
class FileOpener:
    format: Format
    subtype: Subtype
    channels: t.Optional[int] = None
    samplerate: t.Optional[int] = None
    _check: bool = True

    def __post_init__(self):
        if self._check and not is_valid(self.format, self.subtype):
            raise ValueError(f'Bad subtype for {self}')

    @property
    def suffix(self) -> str:
        return f'.{self.format.lower()}'

    def open(self, path: Path, mode: str = 'r') -> sf.SoundFile:
        return sf.SoundFile(
            file=path.with_suffix(self.suffix),
            mode=mode,
            channels=self.channels,
            samplerate=self.samplerate,
            format=self.format.upper(),
            subtype=self.subtype.upper(),
        )
