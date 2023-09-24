import dataclasses as dc
import typing as t
from pathlib import Path

import soundfile as sf

from . import format, subtype


@dc.dataclass(frozen=True)
class FileOpener:
    format: format.Format
    subtype: subtype.Subtype
    channels: t.Optional[int] = None
    samplerate: t.Optional[int] = None

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
