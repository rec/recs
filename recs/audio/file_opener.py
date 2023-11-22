import itertools
from pathlib import Path

import soundfile as sf

from recs.cfg import Cfg, Track
from recs.cfg.metadata import ALLOWS_METADATA


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

        if self.cfg.format in ALLOWS_METADATA:
            for k, v in metadata.items():
                setattr(fp, k, v)

        return fp

    def create(
        self, metadata: dict[str, str], timestamp: float, index: int
    ) -> sf.SoundFile:
        p = Path(self.cfg.path.evaluate(self.track, self.cfg.aliases, timestamp, index))
        p.parent.mkdir(exist_ok=True, parents=True)

        for i in itertools.count():
            f = p.parent / (p.name + bool(i) * f'_{i}')
            try:
                return self.open(f, metadata)
            except FileExistsError:
                pass
