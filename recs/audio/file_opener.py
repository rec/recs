import itertools
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path

import soundfile
from pydantic import BaseModel
from ufor.encoding import Format, Subtype

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
        subtype = self.subtype
        if subtype is None:
            if self.format == Format.flac:
                subtype = (
                    Subtype.pcm_24
                    if soundfile.check_format(self.format, Subtype.pcm_24)
                    else Subtype.pcm_32
                )
            elif soundfile.check_format(self.format, Subtype.float):
                subtype = Subtype.float

        if not overwrite:
            path.touch(exist_ok=False)
        with ExitStack() as cleanup:
            if not overwrite:
                cleanup.callback(path.unlink)
            fp = soundfile.SoundFile(
                channels=self.channels,
                file=path,
                format=self.format,
                mode='w',
                samplerate=self.samplerate,
                subtype=subtype,
            )
            cleanup.callback(fp.close)
            if self.format in ALLOWS_METADATA:
                for k, v in metadata.items():
                    setattr(fp, k, v)
            cleanup.pop_all()
            return fp

    def create(self, metadata: Mapping[str, str], path: Path) -> soundfile.SoundFile:
        path = path.with_suffix('.' + self.format)
        path.parent.mkdir(exist_ok=True, parents=True)

        for i in itertools.count():
            f = path.with_stem(path.stem + (f'_{i}' if i else ''))
            try:
                return self.open(f, metadata)
            except FileExistsError:
                pass
        raise FileNotFoundError
