import dataclasses as dc
from pathlib import Path

from recs.audio.silence import SilenceStrategy

DEFAULT_SILENCE = SilenceStrategy[float](
    at_start=3,
    at_end=3,
    before_stopping=20,
)


@dc.dataclass(frozen=True)
class Config:
    path: Path = Path()
    file_format: str = 'PCM_24'
    silence: SilenceStrategy[float] = DEFAULT_SILENCE
    file_subtype: str = '.flac'
