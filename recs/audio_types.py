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

    def open(self, path: Path | str, mode: str = 'r') -> sf.SoundFile:
        return sf.SoundFile(
            file=str(path),
            mode=mode,
            channels=self.channels,
            samplerate=self.samplerate,
            format=self.format.upper(),
            subtype=self.subtype.upper(),
        )
