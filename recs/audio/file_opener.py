from pathlib import Path

import soundfile as sf

from recs import Cfg
from recs.misc.recording_path import recording_path

from .track import Track


class FileOpener:
    def __init__(self, cfg: Cfg, track: Track) -> None:
        self.cfg = cfg
        self.track = track

    def open(self, path: Path, mode: str = 'r') -> sf.SoundFile:
        path = path.with_suffix('.' + self.cfg.format)
        if path.exists():
            raise FileExistsError(str(path))

        return sf.SoundFile(
            channels=len(self.track.channels),
            file=path,
            format=self.cfg.format,
            mode=mode,
            samplerate=self.track.device.samplerate,
            subtype=self.cfg.subtype,
        )

    def create(self) -> sf.SoundFile:
        index = 0
        suffix = ''
        path, name = recording_path(
            self.track, self.cfg.aliases, self.cfg.subdirectories
        )

        while True:
            p = self.cfg.path / path / (name + suffix)
            p.parent.mkdir(exist_ok=True, parents=True)
            try:
                return self.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'
