import dataclasses as dc
from pathlib import Path

import soundfile as sf

from .file_types import Format, Subtype


@dc.dataclass(frozen=True)
class FileOpener:
    channels: int | None = None
    exist_ok: bool = False
    format: Format | None = None
    samplerate: int | None = None
    subtype: Subtype | None = None
    suffix: str | None = None

    def with_suffix(self, path: Path) -> Path:
        return path.with_suffix(self.suffix) if self.suffix else path

    def open(self, path: Path, mode: str = 'r') -> sf.SoundFile:
        kwargs = dc.asdict(self)
        if not kwargs.pop('exist_ok') and path.exists():
            raise FileExistsError(str(path))
        kwargs.pop('suffix')
        return sf.SoundFile(file=self.with_suffix(path), mode=mode, **kwargs)
