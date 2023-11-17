from pathlib import Path

import soundfile as sf

from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.misc.recording_path import recording_path


class FileOpener:
    def __init__(self, cfg: Cfg, track: Track) -> None:
        self.cfg = cfg
        self.track = track

    def open(
        self, path: Path | str, metadata: dict[str, str], overwrite: bool = False
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

        for k, v in metadata.items():
            setattr(fp, k, v)

        return fp

    def create(self, metadata: dict[str, str], timestamp: float) -> sf.SoundFile:
        index = 0
        suffix = ''
        path, name = recording_path(
            self.track, self.cfg.alias, self.cfg.subdirectory, timestamp
        )

        while True:
            p = self.cfg.path / path / (name + suffix)
            p.parent.mkdir(exist_ok=True, parents=True)
            try:
                return self.open(p, metadata)
            except FileExistsError:
                index += 1
                suffix = f'_{index}'
