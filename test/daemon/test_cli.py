import pytest

from recs.base.errors import RecsError
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
    assert cli.main(['install', '--include', 'Mic']) == 0

    assert controllers[0].metadata.argv == [
        '--silent',
        '--include',
        'Mic',
    ]
    assert '"installed":true' in capsys.readouterr().out


def test_daemon_install_rejects_interactive_options() -> None:
    with pytest.raises(RecsError, match='Cannot install daemon with --gui'):
        cli.main(['install', '--gui'])
    with pytest.raises(RecsError, match='Cannot install daemon with --remote'):
        cli.main(['install', '--remote'])


def test_daemon_install_rejects_root_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)
    monkeypatch.setattr(cli, 'raise_if_root', lambda: _raise_root_error())

    with pytest.raises(RecsError, match='recs daemon must not run as root'):
        cli.main(['install'])


def test_daemon_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)
    monkeypatch.setattr(cli.rpc, 'Client', FakeRpcClient)

    assert cli.main(['status']) == 0

    output = capsys.readouterr().out
    assert 'daemon: yes\n' in output
    assert 'details: active\n' in output


def test_daemon_status_accepts_json_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)
    monkeypatch.setattr(cli.rpc, 'Client', FakeRpcClient)

    assert cli.main(['status', '--json']) == 0

    assert '"running":true' in capsys.readouterr().out


def test_daemon_status_includes_live_recorder_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)
    monkeypatch.setattr(cli.rpc, 'Client', FakeRpcClient)

    assert cli.main(['status']) == 0

    assert capsys.readouterr().out == (
        'daemon: yes\n'
        'installed: yes\n'
        'details: active\n'
        'recording: active\n'
        'session directory: /recordings/2026-08-18 12:00:00\n'
        'manifest: /recordings/2026-08-18 12:00:00/recs-session.jsonl\n'
        'disk: /recordings\n'
        'disk free bytes: 100\n'
        'disk seconds remaining: 2.0\n'
        'files: 3\n'
        'bytes: 456\n'
        'devices: 1/2 online\n'
        'warnings: 1\n'
    )


def test_daemon_status_reports_recorder_connection_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)
    monkeypatch.setattr(cli.rpc, 'Client', BrokenRpcClient)

    assert cli.main(['status']) == 0

    assert capsys.readouterr().out == (
        'daemon: yes\n'
        'installed: yes\n'
        'details: active\n'
        'recorder: unavailable (offline)\n'
    )


def test_daemon_status_rejects_unknown_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.paths, 'current_platform', lambda: 'linux')
    monkeypatch.setattr(cli, 'ServiceController', FakeController)

    with pytest.raises(RecsError, match='Unknown daemon status option'):
        cli.main(['status', '--brief'])


def _raise_root_error() -> None:
    raise RecsError('recs daemon must not run as root')


class FakeRpcClient:
    def __init__(self, endpoint: object, *, role: str) -> None:
        self.endpoint = endpoint
        self.role = role

    def call(self, command: str) -> dict[str, object]:
        assert command == 'status_snapshot'
        return {
            'type': 'status_snapshot_result',
            'recording': {'paused': False},
            'session_directory': '/recordings/2026-08-18 12:00:00',
            'manifest_path': '/recordings/2026-08-18 12:00:00/recs-session.jsonl',
            'disk': {
                'path': '/recordings',
                'free_bytes': 100,
                'estimated_seconds_remaining': 2.0,
            },
            'rows': [{'file_count': 3, 'file_size': 456}],
            'devices': [{'online': True}, {'online': False}],
            'errors': [{'message': 'quiet'}],
        }


class BrokenRpcClient:
    def __init__(self, endpoint: object, *, role: str) -> None:
        pass

    def call(self, command: str) -> dict[str, object]:
        raise ConnectionError('offline')
