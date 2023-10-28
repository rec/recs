import dataclasses as dc

import soundfile as sf

from recs import RECS

from ..misc import legal_filename, recording_path
from . import file_opener, track

TIMESTAMP_FORMAT = '%Y%m%d-%H%M%S'


@dc.dataclass
class FileCreator:
    opener: file_opener.FileOpener
    track: track.Track

    def __call__(self) -> sf.SoundFile:
        index = 0
        suffix = ''
        path, name = recording_path.recording_path(self.track)

        while True:
            p = RECS.path / path / legal_filename.legal_filename(name + suffix)
            p.parent.mkdir(exist_ok=True, parents=True)
            try:
                return self.opener.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'
