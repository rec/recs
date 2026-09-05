import json
from typing import cast

from reccy.protocol import rpc
from reccy.services import models

from recs.base.errors import RecsError

from . import paths, renderers
from .controllers import ServiceController
from .models import StatusResult
from .root_user import raise_if_root

COMMANDS = {'install', 'uninstall', 'start', 'stop', 'restart', 'status'}
INTERACTIVE_OPTIONS = {
    '--calibrate',
    '--gui',
    '--info',
    '--list-types',
    '--remote',
    '--types',
    '--no-silent',
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {'-h', '--help'}:
        print(HELP)
        return 0

    command, args = argv[0], argv[1:]
    if command not in COMMANDS:
        raise RecsError(f'Unknown daemon command: {command}')
    if command == 'status' and args == ['--json']:
        args = []
    if command == 'status' and args:
        raise RecsError(f'Unknown daemon status option: {args[0]}')

    platform = paths.current_platform()
    controller = ServiceController(platform)

    if command == 'install':
        raise_if_root()
        _validate_install_args(args)
        metadata = renderers.metadata(platform, args)
        result = controller.install(metadata)
    elif command == 'uninstall':
        result = controller.uninstall()
    elif command == 'start':
        result = controller.start()
    elif command == 'stop':
        result = controller.stop()
    elif command == 'restart':
        result = controller.restart()
    elif command == 'status':
        result = controller.status()
        status = _status_payload(result, platform)
        if '--json' in argv:
            print(json.dumps(status, separators=(',', ':')))
        else:
            _print_status(status)
        return 0
    else:
        result = controller.status()

    print(result.model_dump_json())
    return 0


def _validate_install_args(args: list[str]) -> None:
    for arg in args:
        if arg in INTERACTIVE_OPTIONS:
            raise RecsError(f'Cannot install daemon with {arg}')


def _status_payload(
    result: StatusResult, platform: models.Platform
) -> dict[str, object]:
    status = result.model_dump(mode='json')
    if not status.get('running'):
        return status
    try:
        status['recorder'] = rpc.Client(
            paths.external_control_endpoint(platform=platform),
            role='status',
        ).call('status_snapshot')
    except (BrokenPipeError, ConnectionError, OSError, TimeoutError) as e:
        status['recorder_error'] = str(e)
    return status


def _print_status(status: dict[str, object]) -> None:
    print(f"daemon: {_state(status.get('running'))}")
    print(f"installed: {_state(status.get('installed'))}")
    if details := status.get('details'):
        print(f'details: {details}')
    if error := status.get('recorder_error'):
        print(f'recorder: unavailable ({error})')
        return
    if not (value := status.get('recorder')) or not isinstance(value, dict):
        return
    recorder = cast(dict[str, object], value)
    recording = recorder.get('recording')
    if isinstance(recording, dict):
        recording = cast(dict[str, object], recording)
        print(f"recording: {'paused' if recording.get('paused') else 'active'}")
    if path := recorder.get('session_directory'):
        print(f'session directory: {path}')
    if path := recorder.get('record_path'):
        print(f'record: {path}')
    if (disk := recorder.get('disk')) and isinstance(disk, dict):
        _print_disk_status(cast(dict[str, object], disk))
    if rows := recorder.get('rows'):
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            total = cast(dict[str, object], rows[0])
            print(f"files: {total.get('file_count', 0)}")
            print(f"bytes: {total.get('file_size', 0)}")
    devices = recorder.get('devices')
    if isinstance(devices, list):
        online = sum(
            1
            for device in devices
            if isinstance(device, dict)
            and cast(dict[str, object], device).get('online')
        )
        print(f'devices: {online}/{len(devices)} online')
    errors = recorder.get('errors')
    if isinstance(errors, list):
        print(f'warnings: {len(errors)}')


def _print_disk_status(disk: dict[str, object]) -> None:
    print(f"disk: {disk.get('path', '')}")
    print(f"disk free bytes: {disk.get('free_bytes', 0)}")
    if remaining := disk.get('estimated_seconds_remaining'):
        print(f'disk seconds remaining: {remaining}')


def _state(value: object) -> str:
    if value is True:
        return 'yes'
    if value is False:
        return 'no'
    return 'unknown'


HELP = """Usage: recs daemon COMMAND [recs options...]

Commands:
  install      Install and start the per-user background recorder.
  uninstall    Stop and remove the per-user background recorder.
  start        Start the installed background recorder.
  stop         Stop the installed background recorder.
  restart      Restart the installed background recorder.
  status       Print daemon installation and running status as JSON.

Install stores the remaining arguments and runs recs with --silent.
"""
