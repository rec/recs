import dataclasses as dc
import enum
from pathlib import Path

import soundfile as sf

Format = enum.StrEnum('Format', list(sf._formats))  # type: ignore[misc]
Subtype = enum.StrEnum('Subtypes', list(sf._subtypes))  # type: ignore[misc]


@dc.dataclass(frozen=True)
class AudioFileFormat:
    channels: int
    samplerate: int
    format: Format
    subtype: Subtype

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
