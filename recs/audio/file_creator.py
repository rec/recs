import dataclasses as dc
from datetime import datetime

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
    track: Track

    def __call__(self) -> sf.SoundFile:
        index = 0
        suffix = ''
        name = self._base_filename()

        while True:
            p = RECS.path / legal_filename(name + suffix)
            try:
                return self.opener.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'

    def _base_filename(self) -> str:
        names = RECS.aliases.display_name(self.track.device), self.track.channels_name
        timestamp = now().strftime(TIMESTAMP_FORMAT)
        return NAME_JOINER.join([*names, timestamp])
