import dataclasses as dc
import enum
from pathlib import Path

import soundfile as sf

Format = enum.StrEnum('Format', list(sf._formats))  # type: ignore[misc]
Subtype = enum.StrEnum('Subtypes', list(sf._subtypes))  # type: ignore[misc]


@dc.dataclass(frozen=True)
class FileFormat:
    channels: int
    samplerate: int
    format: Format
    subtype: Subtype

    def __post_init__(self):
        pass

    def open(self, path: Path | str) -> sf.SoundFile:
        return sf.SoundFile(
            str(path),
            channels=self.channels,
            samplerate=self.samplerate,
            format=self.format.upper(),
            subtype=self.subtype.upper(),
        )
