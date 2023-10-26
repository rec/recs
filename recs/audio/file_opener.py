import dataclasses as dc
from pathlib import Path

import soundfile as sf

from recs import RECS

from .file_types import Subtype


@dc.dataclass(frozen=True)
class FileOpener:
    channels: int
    samplerate: int
    subtype: Subtype | None = None
    exist_ok: bool = False

    def open(self, path: Path, mode: str = 'r') -> sf.SoundFile:
        path = path.with_suffix('.' + RECS.format)
        if not self.exist_ok and path.exists():
            raise FileExistsError(str(path))

        return sf.SoundFile(
            channels=self.channels,
            file=path,
            format=RECS.format,
            mode=mode,
            samplerate=self.samplerate,
            subtype=self.subtype or None,
        )
