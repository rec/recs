import typing as t
from datetime import datetime
from pathlib import Path

from recs.audio.device import InputDevice
from recs.audio.track import Track
from recs.base.aliases import Aliases
from recs.base.types import Subdirectory

from .legal_filename import legal_filename

NAME_JOINER = ' + '


def recording_path(
    track: Track,
    aliases: Aliases,
    subdirectories: t.Sequence[Subdirectory],
    timestamp: float,
) -> tuple[Path, str]:
    def display_name(x: Track | InputDevice) -> str:
        s = aliases.display_name(x)
        return legal_filename(s)

    ts = datetime.fromtimestamp(timestamp)
    time = ts.strftime('%Y/%m/%d')
    hms = ts.strftime('%H%M%S')

    pieces: dict[str, str] = {
        'device': display_name(track.device),
        'channel': display_name(track),
        'time': time,
    }

    paths: list[str] = []

    for s in subdirectories:
        paths.append(pieces.pop(s))

    file_parts = []
    for k, v in pieces.items():
        if k == 'time':
            date = v.replace('/', '')
            hms = f'{date}-{hms}'
        else:
            file_parts.append(v)

    filename = NAME_JOINER.join([*file_parts, hms])
    return Path(*paths), filename
