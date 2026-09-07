from pathlib import Path

import pytest
from reccy.services.models import DaemonMetadata, Platform

from recs.cfg import settings
from recs.daemon import preflight
from recs.daemon.models import StatusResult


class FakeController:
    def __init__(self, platform: Platform) -> None:
        self.platform = platform

    def status(self) -> StatusResult:
        return StatusResult(installed=True, running=True)


class FakeRpcClient:
    def __init__(self, endpoint: object, *, role: str) -> None:
        assert role == 'preflight'


def test_preflight_passes_for_ready_daemon(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    metadata = DaemonMetadata(
        argv=['--silent', '--output-directory', str(tmp_path / 'recordings')],
        module='recs',
        platform=Platform.macos,
        control_endpoint=str(tmp_path / 'gui.sock'),
    )

    class ReadyRpcClient(FakeRpcClient):
        def call(self, command: str) -> dict[str, object]:
            assert command == 'status_snapshot'
            return {
                'session_directory': str(tmp_path / 'recordings/session'),
                'devices': [
                    {'name': 'X18', 'online': True},
                    {'name': 'Flow 8', 'online': True},
                ],
            }

    monkeypatch.setattr(preflight.paths, 'current_platform', lambda: Platform.macos)
    monkeypatch.setattr(preflight, 'ServiceController', FakeController)
    monkeypatch.setattr(preflight.gui_ipc, 'load_metadata', lambda: metadata)
    monkeypatch.setattr(preflight.rpc, 'Client', ReadyRpcClient)
    monkeypatch.setattr(settings, 'settings_path', lambda: tmp_path / 'settings.json')

    assert preflight.main([]) == 0

    assert capsys.readouterr().out == (
        'PASS service: installed and running\n'
        'PASS settings: valid\n'
        'PASS ownership: service and recorder control endpoint agree\n'
        f'PASS output: {tmp_path} is writable\n'
        'PASS devices: 2 online\n'
        'Preflight passed\n'
    )


def test_preflight_reports_offline_device(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
    tmp_path: Path,
) -> None:
    metadata = DaemonMetadata(
        argv=['--silent'],
        module='recs',
        platform=Platform.macos,
        control_endpoint=str(tmp_path / 'gui.sock'),
    )

    class OfflineRpcClient(FakeRpcClient):
        def call(self, command: str) -> dict[str, object]:
            return {
                'session_directory': str(tmp_path),
                'devices': [{'name': 'Flow 8', 'online': False}],
            }

    monkeypatch.setattr(preflight.paths, 'current_platform', lambda: Platform.macos)
    monkeypatch.setattr(preflight, 'ServiceController', FakeController)
    monkeypatch.setattr(preflight.gui_ipc, 'load_metadata', lambda: metadata)
    monkeypatch.setattr(preflight.rpc, 'Client', OfflineRpcClient)
    monkeypatch.setattr(settings, 'settings_path', lambda: tmp_path / 'settings.json')

    checks = preflight.preflight()

    assert checks[-1] == preflight.PreflightCheck(
        name='devices', passed=False, detail='offline: Flow 8'
    )
