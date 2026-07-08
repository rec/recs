from pathlib import Path

from recs.cfg import Cfg, run_cli
from recs.daemon.models import DaemonMetadata, Platform


def test_gui_selects_remote_when_daemon_endpoint_is_reachable(
    monkeypatch,
) -> None:
    metadata = DaemonMetadata(
        executable=Path('/opt/recs/bin/recs'),
        platform=Platform.linux,
        gui_endpoint='/tmp/recs.sock',
    )
    calls: list[str] = []

    monkeypatch.setattr(run_cli.gui_ipc, 'load_metadata', lambda: metadata)
    monkeypatch.setattr(run_cli.gui_ipc, 'endpoint_reachable', lambda value: True)
    monkeypatch.setattr(
        run_cli.gui_ipc,
        'run_remote_gui',
        lambda value, cfg: calls.append('remote'),
    )

    run_cli.run_cli(Cfg(gui=True))

    assert calls == ['remote']


def test_gui_falls_back_when_daemon_endpoint_is_absent(monkeypatch) -> None:
    metadata = DaemonMetadata(
        executable=Path('/opt/recs/bin/recs'),
        platform=Platform.linux,
        gui_endpoint='/tmp/recs.sock',
    )
    calls: list[str] = []

    class FakeRecorder:
        def __init__(self, cfg: Cfg) -> None:
            pass

        def run(self) -> None:
            calls.append('local')

    monkeypatch.setattr(run_cli.gui_ipc, 'load_metadata', lambda: metadata)
    monkeypatch.setattr(run_cli.gui_ipc, 'endpoint_reachable', lambda value: False)
    monkeypatch.setattr(run_cli, 'Recorder', FakeRecorder)

    run_cli.run_cli(Cfg(gui=True))

    assert calls == ['local']
