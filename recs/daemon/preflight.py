import contextlib
import io
import tempfile
from pathlib import Path
from typing import cast

import tyro
from pydantic import BaseModel
from reccy.protocol import ipc, rpc

from recs.base.errors import RecsError
from recs.cfg import cli, run_cli, settings

from . import gui_ipc, paths
from .controllers import ServiceController


class PreflightCommand(BaseModel, frozen=True):
    pass


class PreflightCheck(BaseModel, frozen=True):
    name: str
    passed: bool
    detail: str


def main(argv: list[str]) -> int:
    tyro.cli(PreflightCommand, args=argv, prog='recs preflight')
    checks = preflight()
    for check in checks:
        state = 'PASS' if check.passed else 'FAIL'
        print(f'{state} {check.name}: {check.detail}')
    passed = all(check.passed for check in checks)
    print('Preflight passed' if passed else 'Preflight failed')
    return 0 if passed else 1


def preflight() -> list[PreflightCheck]:
    platform = paths.current_platform()
    status = ServiceController(platform).status()
    service_ok = status.installed and status.running is True
    checks = [
        PreflightCheck(
            name='service',
            passed=service_ok,
            detail=(
                'installed and running'
                if service_ok
                else _service_failure(status.installed, status.running, status.details)
            ),
        )
    ]

    metadata = gui_ipc.load_metadata()
    checks.append(_settings_check(metadata.argv if metadata is not None else None))

    snapshot: dict[str, object] | None = None
    if not service_ok:
        ownership = PreflightCheck(
            name='ownership', passed=False, detail='daemon is not running'
        )
    else:
        try:
            response = rpc.Client(
                paths.external_control_endpoint(platform=platform),
                role='preflight',
            ).call('status_snapshot')
        except (BrokenPipeError, ConnectionError, OSError, TimeoutError) as error:
            ownership = PreflightCheck(
                name='ownership',
                passed=False,
                detail=str(error) or type(error).__name__,
            )
        else:
            if isinstance(response, ipc.Error):
                ownership = PreflightCheck(
                    name='ownership', passed=False, detail=response.message
                )
            elif isinstance(response, dict):
                snapshot = response
                ownership = PreflightCheck(
                    name='ownership',
                    passed=True,
                    detail='service and recorder control endpoint agree',
                )
            else:
                ownership = PreflightCheck(
                    name='ownership',
                    passed=False,
                    detail='recorder returned an invalid status response',
                )
    checks.append(ownership)
    checks.append(_output_check(snapshot))
    checks.append(_device_check(snapshot))
    return checks


def _settings_check(arguments: list[str] | None) -> PreflightCheck:
    if arguments is None:
        return PreflightCheck(
            name='settings',
            passed=False,
            detail='daemon metadata is missing or invalid',
        )
    errors = io.StringIO()
    try:
        with contextlib.redirect_stderr(errors):
            cfg = tyro.cli(cli.CliCfg, args=arguments, prog='recs')
        general = cfg.general.model_copy(update={'save_settings': True})
        cfg = cfg.model_copy(update={'general': general})
        settings.load(cfg, run_cli.cli_overrides(arguments))
    except (RecsError, SystemExit) as error:
        detail = errors.getvalue().strip() or str(error) or 'invalid daemon arguments'
        return PreflightCheck(name='settings', passed=False, detail=detail)
    return PreflightCheck(name='settings', passed=True, detail='valid')


def _output_check(snapshot: dict[str, object] | None) -> PreflightCheck:
    if snapshot is None:
        return PreflightCheck(
            name='output', passed=False, detail='recorder status is unavailable'
        )
    path_value = snapshot.get('session_directory')
    if not isinstance(path_value, str) or not path_value:
        return PreflightCheck(
            name='output', passed=False, detail='session directory is unavailable'
        )
    path = Path(path_value)
    parent = next((p for p in (path, *path.parents) if p.exists()), None)
    if parent is None:
        return PreflightCheck(
            name='output', passed=False, detail=f'{path}: no existing parent directory'
        )
    try:
        with tempfile.NamedTemporaryFile(prefix='.recs-preflight-', dir=parent):
            pass
    except OSError as error:
        return PreflightCheck(name='output', passed=False, detail=f'{parent}: {error}')
    return PreflightCheck(name='output', passed=True, detail=f'{parent} is writable')


def _device_check(snapshot: dict[str, object] | None) -> PreflightCheck:
    if snapshot is None:
        return PreflightCheck(
            name='devices', passed=False, detail='recorder status is unavailable'
        )
    values = snapshot.get('devices')
    if not isinstance(values, list) or not values:
        return PreflightCheck(
            name='devices', passed=False, detail='no configured audio devices'
        )
    devices = [cast(dict[str, object], d) for d in values if isinstance(d, dict)]
    offline = sorted(
        str(d.get('name', 'unknown')) for d in devices if not d.get('online')
    )
    if offline:
        return PreflightCheck(
            name='devices',
            passed=False,
            detail=f'offline: {", ".join(offline)}',
        )
    return PreflightCheck(name='devices', passed=True, detail=f'{len(devices)} online')


def _service_failure(installed: bool, running: bool | None, details: str) -> str:
    if not installed:
        return 'not installed'
    if running is not True:
        return details or 'not running'
    return details or 'unavailable'
