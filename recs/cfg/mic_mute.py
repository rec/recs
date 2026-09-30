"""Machine-wide, name-based exclusion of a possible room microphone."""

import os
import re
import sys
from pathlib import Path

import tyro
from pydantic import BaseModel, ConfigDict, ValidationError
from reccy.configuration.settings import write_json_model
from reccy.device import DeviceDict

from recs.base.errors import RecsError


class MicMute(BaseModel):
    device_name: str
    is_muted: bool

    model_config = ConfigDict(frozen=True)


class MuteCommand(BaseModel, frozen=True):
    clear: bool = False


def candidates(devices: list[DeviceDict]) -> list[DeviceDict]:
    return [
        d
        for d in devices
        if d.get('max_input_channels') in (1, 2) and d.get('max_output_channels') == 0
    ]


def resolve(devices: list[DeviceDict]) -> tuple[MicMute | None, str | None]:
    if (saved := load()) is not None:
        if saved.is_muted and not any(
            d.get('name') == saved.device_name for d in devices
        ):
            return (
                saved,
                f'WARNING: muted mic {saved.device_name} not found - '
                'room mic may not be muted; use `recs mute` to choose again.',
            )
        return saved, None
    found = candidates(devices)
    if not found:
        return None, None
    matching = [
        d for d in found if re.search(r'\bmicrophone\b', str(d['name']), re.IGNORECASE)
    ]
    if len(matching) == 1:
        name = str(matching[0]['name'])
        return (
            MicMute(device_name=name, is_muted=True),
            f'WARNING: muted possible room mic {name} - '
            'use `recs mute` to silence this warning.',
        )
    return (
        None,
        'WARNING: room mic not muted - use `recs mute` to silence this warning.',
    )


def load() -> MicMute | None:
    path = mic_mute_path()
    try:
        return MicMute.model_validate_json(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValidationError) as error:
        raise RecsError(f'Could not read mic mute from {path}: {error}') from None


def save(mute: MicMute) -> None:
    path = mic_mute_path()
    try:
        write_json_model(path, mute, indent=2)
    except OSError as error:
        raise RecsError(f'Could not save mic mute to {path}: {error}') from None


def clear() -> None:
    try:
        mic_mute_path().unlink(missing_ok=True)
    except OSError as error:
        raise RecsError(f'Could not clear mic mute: {error}') from None


def mic_mute_path() -> Path:
    if sys.platform == 'win32':
        appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
        return appdata / 'recs' / 'mic-mute.json'
    return Path.home() / '.config/recs/mic-mute.json'


def main(argv: list[str]) -> int:
    command = tyro.cli(MuteCommand, args=argv, prog='recs mute')
    if command.clear:
        clear()
        return 0

    from .device import query_devices

    found = candidates(list(query_devices()))
    if not found:
        sys.exit('ERROR: no microphones found')
    if len(found) == 1:
        name = str(found[0]['name'])
        response = _answer(f'Mute {name}? (Y/n) ').casefold()
        if response not in ('', 'y', 'yes', 'n', 'no'):
            raise RecsError(f'Invalid answer: {response}')
        save(MicMute(device_name=name, is_muted=response in ('', 'y', 'yes')))
        return 0

    for index, candidate in enumerate(found, 1):
        print(f'{index}. {candidate["name"]}')
    print(f'{len(found) + 1}. No mute')
    response = _answer('Select: ')
    if not response.isdecimal() or not 1 <= int(response) <= len(found) + 1:
        raise RecsError(f'Invalid selection: {response}')
    selection = int(response) - 1
    if selection == len(found):
        save(MicMute(device_name='', is_muted=False))
        return 0
    name = str(found[selection]['name'])
    if sum(candidate['name'] == name for candidate in found) > 1:
        raise RecsError(f'Cannot distinguish microphones named {name}')
    save(MicMute(device_name=name, is_muted=True))
    return 0


def _answer(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise RecsError('No answer received') from None
