import dataclasses as dc
from pathlib import Path

import soundfile as sf

from .file_types import Format, Subtype


@dc.dataclass(frozen=True)
class FileOpener:
    channels: int | None = None
    exist_ok: bool = False
    format: Format = Format.none
    samplerate: int | None = None
    subtype: Subtype = Subtype.none

    def open(self, path: Path, mode: str = 'r') -> sf.SoundFile:
        if not self.exist_ok and path.exists():
            raise FileExistsError(str(path))

        return sf.SoundFile(
            channels=self.channels,
            file=path,
            format=self.format or None,
            mode=mode,
            samplerate=self.samplerate,
            subtype=self.subtype or None,
        )
