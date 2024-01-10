import dataclasses as dc
import itertools
import typing as t
from pathlib import Path

import soundfile as sf

from recs.base.types import Format, Subtype
from recs.cfg.metadata import ALLOWS_METADATA


@dc.dataclass
class FileOpener:
    format: Format
    channels: int = 1
    samplerate: int = 48_000
    subtype: Subtype | None = None

    def open(
        self, path: Path | str, metadata: t.Mapping[str, str], overwrite: bool = False
    ) -> sf.SoundFile:
        path = Path(path).with_suffix('.' + self.format)
        if not overwrite and path.exists():
            raise FileExistsError(str(path))

        fp = sf.SoundFile(
            channels=self.channels,
            file=path,
            format=self.format,
            mode='w',
            samplerate=self.samplerate,
            subtype=self.subtype,
        )

        if self.format in ALLOWS_METADATA:
            for k, v in metadata.items():
                setattr(fp, k, v)

        return fp

    def create(self, metadata: t.Mapping[str, str], path: Path) -> sf.SoundFile:
        path.parent.mkdir(exist_ok=True, parents=True)

        for i in itertools.count():
            f = path.parent / (path.name + bool(i) * f'_{i}')
            try:
                return self.open(f, metadata)
            except FileExistsError:
                pass
