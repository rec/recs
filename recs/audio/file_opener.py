from pathlib import Path

import soundfile as sf

from recs import Cfg
from recs.misc.recording_path import recording_path

from ..base import to_time
from .track import Track

URL = 'https://github.com/rec/recs'


class FileOpener:
    def __init__(self, cfg: Cfg, track: Track) -> None:
        self.cfg = cfg
        self.track = track

    def open(
        self, path: Path | str, tracknumber: int, overwrite: bool = False
    ) -> sf.SoundFile:
        path = Path(path).with_suffix('.' + self.cfg.format)
        if not overwrite and path.exists():
            raise FileExistsError(str(path))

        fp = sf.SoundFile(
            channels=len(self.track.channels),
            file=path,
            format=self.cfg.format,
            mode='w',
            samplerate=self.track.device.samplerate,
            subtype=self.cfg.subtype,
        )

        t = str(tracknumber)
        metadata = dict(date=to_time.now().isoformat(), software=URL, tracknumber=t)
        metadata |= self.cfg.metadata

        for k, v in metadata.items():
            setattr(fp, k, v)

        return fp

    def create(self, tracknumber: int) -> sf.SoundFile:
        index = 0
        suffix = ''
        path, name = recording_path(self.track, self.cfg.alias, self.cfg.subdirectory)

        while True:
            p = self.cfg.path / path / (name + suffix)
            p.parent.mkdir(exist_ok=True, parents=True)
            try:
                return self.open(p, tracknumber)
            except FileExistsError:
                index += 1
                suffix = f'_{index}'
