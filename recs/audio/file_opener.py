import dataclasses as dc
from pathlib import Path

import soundfile as sf

from recs import RECS
from recs.misc.recording_path import recording_path

from .track import Track


@dc.dataclass(frozen=True)
class FileOpener:
    track: Track

    def open(self, path: Path, mode: str = 'r') -> sf.SoundFile:
        path = path.with_suffix('.' + RECS.format)
        if path.exists():
            raise FileExistsError(str(path))

        return sf.SoundFile(
            channels=len(self.track.channels),
            file=path,
            format=RECS.format,
            mode=mode,
            samplerate=self.track.device.samplerate,
            subtype=RECS.subtype,
        )

    def create(self) -> sf.SoundFile:
        index = 0
        suffix = ''
        path, name = recording_path(self.track)

        while True:
            p = RECS.path / path / (name + suffix)
            p.parent.mkdir(exist_ok=True, parents=True)
            try:
                return self.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'
