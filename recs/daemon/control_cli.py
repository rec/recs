import json
import sys
from collections.abc import Callable
from typing import Annotated, ClassVar

import tyro
from pydantic import BaseModel, ValidationError
from reccy.protocol import rpc

from . import paths


class ControlCommand(BaseModel, frozen=True):
    rpc_command: ClassVar[str]


class Status(ControlCommand):
    rpc_command = 'status_snapshot'


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
    rpc_command = 'pause_recording'


class Resume(ControlCommand):
    rpc_command = 'resume_recording'


class Calibrate(ControlCommand):
    rpc_command = 'calibrate'


class CardReplace(ControlCommand):
    rpc_command = 'card_replace'


class ReloadProfiles(ControlCommand):
    rpc_command = 'reload_profiles'


def main(argv: list[str]) -> int:
    command = tyro.extras.subcommand_cli_from_dict(
        COMMANDS,
        args=argv,
        prog='recs control',
        description='Send one command to the running Recs daemon.',
    )
    params = command.model_dump()
    if isinstance(command, Set):
        params['value'] = _json_or_string(command.value)
    try:
        result = rpc.Client(
            paths.external_control_endpoint(),
            role='recs-control',
            timeout=6,
        ).call(command.rpc_command, **params)
    except (OSError, ValidationError) as error:
        print(str(error) or type(error).__name__, file=sys.stderr)
        return 1
    print(json.dumps(result, separators=(',', ':')))
    return 0


def _json_or_string(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


COMMANDS: dict[str, Callable[..., ControlCommand]] = {
    'status': Status,
    'disk': Disk,
    'devices': Devices,
    'capabilities': Capabilities,
    'mutable': Mutable,
    'get': Get,
    'set': Set,
    'mark': Mark,
    'pause': Pause,
    'resume': Resume,
    'calibrate': Calibrate,
    'card-replace': CardReplace,
    'reload-profiles': ReloadProfiles,
}
