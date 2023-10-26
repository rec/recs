import dataclasses as dc
from datetime import datetime
from pathlib import Path

import soundfile as sf

from recs import RECS
from recs.audio.legal_filename import legal_filename
from recs.ui.track import Track

from . import file_opener

NAME_JOINER = ' + '
TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'

now = datetime.now
RECS.verbose


@dc.dataclass
class FileCreator:
    opener: file_opener.FileOpener
    path: Path
    track: Track

    def __call__(self) -> sf.SoundFile:
        index = 0
        suffix = ''
        names = RECS.aliases.display_name(self.track.device), self.track.channels_name
        name = NAME_JOINER.join((*names, self._timestamp()))

        while True:
            p = self.path / legal_filename(name + suffix)
            try:
                return self.opener.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'

    def _timestamp(self) -> str:
        return now().strftime(TIMESTAMP_FORMAT)
