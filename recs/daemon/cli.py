import shutil
import sys
from pathlib import Path

from recs.base import RecsError

from . import paths, renderers
from .controllers import ServiceController

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
        _validate_install_args(args)
        metadata = renderers.metadata(_executable(), platform, args)
        result = controller.install(metadata)
    elif command == 'uninstall':
        result = controller.uninstall()
    elif command == 'start':
        result = controller.start()
    elif command == 'stop':
        result = controller.stop()
    elif command == 'restart':
        result = controller.restart()
    else:
        result = controller.status()

    print(result.model_dump_json())
    return 0


def _validate_install_args(args: list[str]) -> None:
    for arg in args:
        if arg in INTERACTIVE_OPTIONS:
            raise RecsError(f'Cannot install daemon with {arg}')


def _executable() -> Path:
    argv0 = Path(sys.argv[0])
    if argv0.parent != Path('.'):
        return argv0.resolve()

    if path := shutil.which(argv0.name):
        return Path(path).resolve()
    if path := shutil.which('recs'):
        return Path(path).resolve()
    return argv0.resolve()


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
