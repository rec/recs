import json
import sys
from collections.abc import Callable
from typing import Annotated, ClassVar

import tomlkit
import tyro
from pydantic import BaseModel, Field, ValidationError
from reccy.protocol import rpc

from . import instances


class ControlCommand(BaseModel, frozen=True):
    rpc_command: ClassVar[str]


class Status(ControlCommand):
    rpc_command = 'status_snapshot'


class Instances(ControlCommand):
    """List running instances without selecting a target."""


class Disk(ControlCommand):
    rpc_command = 'disk_status'


class Devices(ControlCommand):
    rpc_command = 'list_devices'


class Capabilities(ControlCommand):
    rpc_command = 'capabilities'


class Mutable(ControlCommand):
    rpc_command = 'mutable_attributes'


class Get(ControlCommand):
    rpc_command = 'get_cfg'
    address: Annotated[str, tyro.conf.Positional]


class Set(ControlCommand):
    rpc_command = 'set_cfg'
    address: Annotated[str, tyro.conf.Positional]
    value: Annotated[str, tyro.conf.Positional]


class Mark(ControlCommand):
    rpc_command = 'mark'
    label: Annotated[str, tyro.conf.Positional]


class Pause(ControlCommand):
    """Pause capture and release input devices; this is not a playback pause."""

    rpc_command = 'pause_recording'


class Play(ControlCommand):
    """Play a recorded session, temporarily pausing capture if it is active."""

    rpc_command = 'play_session'
    session: int = -1
    source: str | None = None
    channel: str | None = None
    output_channel: str | None = None


class Stop(ControlCommand):
    """Stop playback; restore capture only if playback owned the capture pause."""

    rpc_command = 'stop_playback'


class PausePlayback(ControlCommand):
    """Pause playback without resuming capture."""

    rpc_command = 'pause_playback'


class Continue(ControlCommand):
    """Continue paused playback, not capture."""

    rpc_command = 'continue_playback'


class Jump(ControlCommand):
    rpc_command = 'jump_playback'
    seconds: Annotated[float, tyro.conf.Positional]


class JumpSession(ControlCommand):
    rpc_command = 'jump_session'
    offset: Annotated[int, tyro.conf.Positional]


class Resume(ControlCommand):
    """Resume capture, first stopping any active playback."""

    rpc_command = 'resume_recording'


class Calibrate(ControlCommand):
    rpc_command = 'calibrate'


class CardReplace(ControlCommand):
    rpc_command = 'card_replace'


class ReloadProfiles(ControlCommand):
    """Reload per-device JSON defaults from --profiles, not a recording project."""

    rpc_command = 'reload_profiles'


class ProjectSwitch(ControlCommand):
    """Switch mutable configuration to a named project or the default workspace."""

    rpc_command = 'switch_project'
    names: Annotated[list[str], tyro.conf.Positional] = Field(default_factory=list)


class MusicianAdd(ControlCommand):
    rpc_command = 'add_musician'
    nickname: Annotated[str, tyro.conf.Positional]
    names: Annotated[list[str], tyro.conf.arg(name='name')] = Field(
        default_factory=list
    )
    public_keys: Annotated[list[str], tyro.conf.arg(name='public-key')] = Field(
        default_factory=list
    )
    links: Annotated[list[str], tyro.conf.arg(name='link')] = Field(
        default_factory=list
    )


class MusicianList(ControlCommand):
    rpc_command = 'list_musicians'


class MusicianEdit(ControlCommand):
    rpc_command = 'edit_musician'
    nickname: Annotated[str, tyro.conf.Positional]
    names: Annotated[list[str] | None, tyro.conf.arg(name='name')] = None
    public_keys: Annotated[list[str] | None, tyro.conf.arg(name='public-key')] = None
    links: Annotated[list[str] | None, tyro.conf.arg(name='link')] = None
    clear_names: bool = False
    clear_public_keys: bool = False
    clear_links: bool = False


class MusicianDelete(ControlCommand):
    rpc_command = 'delete_musician'
    nickname: Annotated[str, tyro.conf.Positional]


class MusicianAssign(ControlCommand):
    rpc_command = 'assign_musician'
    nickname: Annotated[str, tyro.conf.Positional]
    source: Annotated[str, tyro.conf.Positional]
    channels: Annotated[list[int], tyro.conf.Positional]
    track_name: str | bool = True


class MusicianRemove(ControlCommand):
    rpc_command = 'remove_musician'
    nickname: Annotated[str, tyro.conf.Positional]
    source: str | None = None
    channels: Annotated[list[int], tyro.conf.arg(name='channel')] = Field(
        default_factory=list
    )


def main(argv: list[str]) -> int:
    try:
        selector, arguments = instances.selector_arguments(argv)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    command = tyro.extras.subcommand_cli_from_dict(
        COMMANDS,
        args=arguments,
        prog='recs control',
        description='Send one command to a running recs instance.',
    )
    if isinstance(command, Instances):
        if selector != instances.Selector():
            print(
                'recs control instances does not accept a target selector',
                file=sys.stderr,
            )
            return 1
        print(json.dumps(instances.list_instances(), separators=(',', ':')))
        return 0
    params = command.model_dump()
    if isinstance(command, Set):
        params['value'] = _json_or_string(command.value)
    if isinstance(command, ProjectSwitch):
        if len(command.names) > 1:
            print('project-switch accepts at most one project name', file=sys.stderr)
            return 1
        params = {'project_name': command.names[0] if command.names else None}
    if isinstance(command, MusicianAdd):
        params = {
            'musician': {
                'nickname': command.nickname,
                'names': command.names,
                'public_keys': command.public_keys,
                'links': command.links,
            }
        }
    try:
        target = instances.resolve(selector)
        result = rpc.Client(
            target.control_endpoint,
            role='recs-control',
            timeout=6,
        ).call(command.rpc_command, **params)
    except (OSError, TimeoutError, ValidationError, ValueError) as error:
        print(str(error) or type(error).__name__, file=sys.stderr)
        return 1
    if isinstance(command, MusicianList):
        if not isinstance(result, dict):
            print('Invalid musician-list response', file=sys.stderr)
            return 1
        print(tomlkit.dumps({'musicians': result['musicians']}), end='')
    else:
        print(json.dumps(result, separators=(',', ':')))
    return 0


def _json_or_string(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


COMMANDS: dict[str, Callable[..., ControlCommand]] = {
    'instances': Instances,
    'status': Status,
    'disk': Disk,
    'devices': Devices,
    'capabilities': Capabilities,
    'mutable': Mutable,
    'get': Get,
    'set': Set,
    'mark': Mark,
    'pause': Pause,
    'play': Play,
    'stop': Stop,
    'pause-playback': PausePlayback,
    'continue': Continue,
    'jump': Jump,
    'jump-session': JumpSession,
    'resume': Resume,
    'calibrate': Calibrate,
    'card-replace': CardReplace,
    'reload-profiles': ReloadProfiles,
    'project-switch': ProjectSwitch,
    'musician-add': MusicianAdd,
    'musician-list': MusicianList,
    'musician-edit': MusicianEdit,
    'musician-delete': MusicianDelete,
    'musician-assign': MusicianAssign,
    'musician-remove': MusicianRemove,
}
