from pathlib import Path

import pytest
from reccy.models import DaemonMetadata, Platform

from recs.base.errors import RecsError
from recs.cfg import run_cli
from recs.cfg.cfg import Cfg
from recs.daemon.models import ServicePaths


def test_remote_selects_daemon_when_endpoint_is_reachable(
    monkeypatch,
) -> None:
    metadata = DaemonMetadata(
        module='recs',
        platform=Platform.linux,
        control_endpoint='/tmp/recs.sock',
    )
    calls: list[str] = []

    monkeypatch.setattr(run_cli.gui_ipc, 'load_metadata', lambda: metadata)
    monkeypatch.setattr(run_cli.gui_ipc, 'endpoint_reachable', lambda value: True)
    monkeypatch.setattr(
        run_cli.gui_ipc,
        'run_remote_gui',
        lambda value, cfg: calls.append('remote'),
    )

    run_cli.run_cli(Cfg(remote=True))

    assert calls == ['remote']


def test_remote_fails_when_daemon_metadata_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_cli.gui_ipc, 'load_metadata', lambda: None)

    with pytest.raises(RecsError, match='recs daemon is not running'):
        run_cli.run_cli(Cfg(remote=True))


def test_remote_fails_when_daemon_endpoint_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = DaemonMetadata(
        module='recs',
        platform=Platform.linux,
        control_endpoint='/tmp/recs.sock',
    )

    monkeypatch.setattr(run_cli.gui_ipc, 'load_metadata', lambda: metadata)
    monkeypatch.setattr(run_cli.gui_ipc, 'endpoint_reachable', lambda value: False)

    with pytest.raises(RecsError, match='recs daemon is not running'):
        run_cli.run_cli(Cfg(remote=True))


def test_default_mode_does_not_check_for_daemon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeRecorder:
        def __init__(self, cfg: Cfg) -> None:
            pass

        def run(self) -> None:
            calls.append('local')

    def load_metadata() -> object:
        raise AssertionError('daemon metadata should not be loaded')

    monkeypatch.setattr(run_cli.gui_ipc, 'load_metadata', load_metadata)
    monkeypatch.setattr(run_cli, 'Recorder', FakeRecorder)

    run_cli.run_cli(Cfg(gui=True))

    assert calls == ['local']


def test_daemon_runtime_rejects_root_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_cli.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(run_cli, 'raise_if_root', lambda: _raise_root_error())

    with pytest.raises(RecsError, match='recs daemon must not run as root'):
        run_cli.run_cli(Cfg())


def test_daemon_startup_failure_writes_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    service_paths = ServicePaths(
        metadata=tmp_path / 'metadata.json',
        service=tmp_path / 'service',
        status=tmp_path / 'status.json',
        log=tmp_path / 'recs.log',
        gui_endpoint=tmp_path / 'gui.sock',
    )
    monkeypatch.setattr(run_cli.gui_ipc, 'daemon_mode_enabled', lambda: True)
    monkeypatch.setattr(run_cli, 'raise_if_root', lambda: None)
    monkeypatch.setattr(run_cli.paths, 'service_paths', lambda platform: service_paths)
    monkeypatch.setattr(run_cli.settings, 'load', _raise_settings_error)

    with pytest.raises(RecsError, match='bad settings'):
        run_cli.run_cli(Cfg())

    assert 'bad settings' in service_paths.status.read_text()


def _raise_root_error() -> None:
    raise RecsError('recs daemon must not run as root')


def _raise_settings_error(cfg: Cfg, overrides: set[str]) -> object:
    raise RecsError('bad settings')
