import dataclasses as dc
import typing as t
from datetime import datetime
from pathlib import Path

import soundfile as sf

from recs.audio.legal_filename import legal_filename

from . import file_opener

NAME_JOINER = ' + '
TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'

now = datetime.now


@dc.dataclass
class FileCreator:
    names: t.Sequence[str]
    opener: file_opener.FileOpener
    path: Path

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
        return now().strftime(TIMESTAMP_FORMAT)
