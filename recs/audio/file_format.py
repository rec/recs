import dataclasses as dc
import typing as t
from pathlib import Path

import soundfile as sf

from .format import Format
from .subtype import Subtype


@dc.dataclass(frozen=True)
class AudioFileFormat:
    format: Format
    subtype: Subtype
    channels: t.Optional[int] = None
    samplerate: t.Optional[int] = None

    @property
    def suffix(self) -> str:
        return f'.{self.format.lower()}'

    def open(self, path: Path | str, mode: str = 'r') -> sf.SoundFile:
        file = str(Path(path).with_suffix(self.suffix))
        print('Opening', file, 'for', mode)
        return sf.SoundFile(
            file=file,
            mode=mode,
            channels=self.channels,
            samplerate=self.samplerate,
            format=self.format.upper(),
            subtype=self.subtype.upper(),
        )
