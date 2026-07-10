from pathlib import Path

import pytest

from recs.base import RecsError
from recs.daemon import cli
from recs.daemon.models import StatusResult


class FakeController:
    def __init__(self, platform: object) -> None:
        self.platform = platform

    def install(self, metadata: object) -> StatusResult:
        self.metadata = metadata
        return StatusResult(installed=True, running=True)

    def uninstall(self) -> StatusResult:
        return StatusResult(installed=False, running=False)

    def start(self) -> StatusResult:
        return StatusResult(installed=True, running=True)

    def stop(self) -> StatusResult:
        return StatusResult(installed=True, running=False)

    def restart(self) -> StatusResult:
        return StatusResult(installed=True, running=True)

    def status(self) -> StatusResult:
        return StatusResult(installed=True, running=True, details='active')


def test_daemon_install_stores_recording_args(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    controllers: list[FakeController] = []

    def make_controller(platform: object) -> FakeController:
        controller = FakeController(platform)
        controllers.append(controller)
        return controller

    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', make_controller)
    monkeypatch.setattr(cli, '_executable', lambda: Path('/opt/recs/bin/recs'))

    assert cli.main(['install', '--include', 'Mic']) == 0

    assert controllers[0].metadata.argv == ['--silent', '--include', 'Mic']
    assert '"installed":true' in capsys.readouterr().out


def test_daemon_install_rejects_interactive_options() -> None:
    with pytest.raises(RecsError, match='Cannot install daemon with --gui'):
        cli.main(['install', '--gui'])
    with pytest.raises(RecsError, match='Cannot install daemon with --remote'):
        cli.main(['install', '--remote'])


def test_daemon_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)

    assert cli.main(['status']) == 0

    assert '"details":"active"' in capsys.readouterr().out


def test_daemon_status_accepts_json_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)

    assert cli.main(['status', '--json']) == 0

    assert '"running":true' in capsys.readouterr().out


def test_daemon_status_rejects_unknown_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)

    with pytest.raises(RecsError, match='Unknown daemon status option'):
        cli.main(['status', '--brief'])
