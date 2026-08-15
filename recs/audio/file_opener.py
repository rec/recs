import itertools
from collections.abc import Mapping
from pathlib import Path

import soundfile
from pydantic import BaseModel

from recs.base.types import Format, Subtype
from recs.cfg.metadata import ALLOWS_METADATA


class FileOpener(BaseModel):
    format: Format
    channels: int = 1
    samplerate: int = 48_000
    subtype: Subtype | None = None

    def open(
        self, path: Path | str, metadata: Mapping[str, str], overwrite: bool = False
    ) -> soundfile.SoundFile:
        path = Path(path).with_suffix('.' + self.format)
        if not overwrite and path.exists():
            raise FileExistsError(str(path))

        subtype = self.subtype
        if subtype is None and soundfile.check_format(self.format, Subtype.float):
            subtype = Subtype.float

        fp = soundfile.SoundFile(
            channels=self.channels,
            file=path,
            format=self.format,
            mode='w',
            samplerate=self.samplerate,
            subtype=subtype,
        )

        if self.format in ALLOWS_METADATA:
            for k, v in metadata.items():
                setattr(fp, k, v)

        return fp

    def create(self, metadata: Mapping[str, str], path: Path) -> soundfile.SoundFile:
        path.parent.mkdir(exist_ok=True, parents=True)

        for i in itertools.count():
            f = path.parent / (path.name + bool(i) * f'_{i}')
            try:
                return self.open(f, metadata)
            except FileExistsError:
                pass
        raise FileNotFoundError
