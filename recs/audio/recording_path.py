from datetime import datetime
from pathlib import Path

from recs import RECS

from .device import InputDevice
from .legal_filename import legal_filename
from .track import Track

now = datetime.now

NAME_JOINER = ' + '


def recording_path(track: Track) -> tuple[Path, str]:
    def display_name(x: Track | InputDevice) -> str:
        s = RECS.aliases.display_name(x)
        return legal_filename(s)

    ts = now()
    time = ts.strftime('%Y/%m/%d')
    hms = ts.strftime('%H%M%S')

    pieces: dict[str, str] = {
        'device': display_name(track.device),
        'channel': display_name(track),
        'time': time,
    }

    paths: list[str] = []

    for s in RECS.subdirectories:
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
