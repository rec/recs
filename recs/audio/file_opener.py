import dataclasses as dc
from pathlib import Path

import soundfile as sf

from .file_types import Subtype


@dc.dataclass(frozen=True)
class FileOpener:
    channels: int
    samplerate: int
    exist_ok: bool = False

    def open(self, path: Path, mode: str = 'r') -> sf.SoundFile:
        from recs import RECS

        path = path.with_suffix('.' + RECS.format)
        if not self.exist_ok and path.exists():
            raise FileExistsError(str(path))

        return sf.SoundFile(
            channels=self.channels,
            file=path,
            format=RECS.format,
            mode=mode,
            samplerate=self.samplerate,
            subtype=None and RECS.subtype,
        )
