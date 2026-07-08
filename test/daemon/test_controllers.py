import subprocess as sp
from pathlib import Path

import pytest

from recs.daemon import controllers
from recs.daemon.controllers import ServiceController
from recs.daemon.models import DaemonMetadata, Platform
from recs.daemon.renderers import metadata


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(
        self,
        command: list[str],
        *,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> sp.CompletedProcess[str]:
        self.commands.append(command)
        return sp.CompletedProcess(
            args=command,
            returncode=0,
            stdout='active\n' if capture_output else '',
            stderr='',
        )


def test_linux_controller_installs_user_service(tmp_path: Path) -> None:
    runner = FakeRunner()
    controller = ServiceController(Platform.linux, tmp_path, runner)
    daemon_metadata = metadata(
        Path('/opt/recs/bin/recs'), Platform.linux, ['--include', 'Mic']
    )

    result = controller.install(daemon_metadata)

    assert result.installed
    assert result.running
    assert controller.paths.metadata.exists()
    assert controller.paths.service.exists()
    assert runner.commands == [
        ['systemctl', '--user', 'daemon-reload'],
        ['systemctl', '--user', 'enable', 'recs.service'],
        ['systemctl', '--user', 'start', 'recs.service'],
    ]


def test_macos_controller_installs_launch_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = FakeRunner()
    monkeypatch.setattr(controllers, '_uid', lambda: 501)
    controller = ServiceController(Platform.macos, tmp_path, runner)
    daemon_metadata = metadata(
        Path('/opt/recs/bin/recs'), Platform.macos, ['--include', 'Mic']
    )

    controller.install(daemon_metadata)

    assert controller.paths.metadata.exists()
    assert controller.paths.service.exists()
    assert runner.commands == [
        [
            'launchctl',
            'bootstrap',
            'gui/501',
            str(controller.paths.service),
        ]
    ]


def test_controller_writes_metadata_atomically(tmp_path: Path) -> None:
    controller = ServiceController(Platform.linux, tmp_path, FakeRunner())
    daemon_metadata = metadata(
        Path('/opt/recs/bin/recs'), Platform.linux, ['--include', 'Mic']
    )

    controller.install(daemon_metadata)

    assert (
        DaemonMetadata.model_validate_json(controller.paths.metadata.read_text())
        == daemon_metadata
    )
    assert not controller.paths.metadata.with_name('.daemon.json.tmp').exists()


def test_status_uses_platform_command(tmp_path: Path) -> None:
    runner = FakeRunner()
    controller = ServiceController(Platform.linux, tmp_path, runner)

    result = controller.status()

    assert not result.installed
    assert result.running
    assert result.details == 'active'
    assert runner.commands == [
        ['systemctl', '--user', 'is-active', 'recs.service']
    ]
