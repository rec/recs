import dataclasses as dc
import typing as t
from datetime import datetime
from pathlib import Path

import soundfile as sf

from recs.audio.legal_filename import legal_filename
from recs.recs import TIMESTAMP_FORMAT

from . import file_opener

NAME_JOINER = ' + '

now = datetime.now


@dc.dataclass
class FileCreator:
    names: t.Sequence[str]
    opener: file_opener.FileOpener
    path: Path
    timestamp_format: str = TIMESTAMP_FORMAT

    def __call__(self) -> sf.SoundFile:
        index = 0
        suffix = ''
        name = NAME_JOINER.join((*self.names, self._timestamp()))

        while True:
            p = self.path / legal_filename(name + suffix)
            try:
                return self.opener.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'

    def _timestamp(self) -> str:
        return now().strftime(self.timestamp_format)
