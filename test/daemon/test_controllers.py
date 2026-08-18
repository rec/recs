import subprocess
from pathlib import Path

import pytest
from reccy import service
from reccy.models import DaemonMetadata, Platform, ServiceSpec

from recs.daemon.controllers import ServiceController
from recs.daemon.models import DaemonStatus
from recs.daemon.renderers import metadata, service_metadata


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
    ) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='active\n' if capture_output else '',
            stderr='',
        )


def test_linux_controller_installs_user_service(tmp_path: Path) -> None:
    runner = FakeRunner()
    controller = ServiceController(Platform.linux, tmp_path, runner)
    daemon_metadata = metadata(Platform.linux, ['--include', 'Mic'])

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


def test_linux_controller_supports_custom_service_identity(tmp_path: Path) -> None:
    service = ServiceSpec(
        name='lyte',
        display_name='lyte',
        description='lyte lighting daemon',
        launchd_label='com.swirly.lyte',
        daemon_env_var='LYTE_DAEMON',
        windows_pipe=r'\\.\pipe\lyte',
    )
    runner = FakeRunner()
    controller = ServiceController(Platform.linux, tmp_path, runner, service)
    service_paths = controller.paths
    daemon_metadata = service_metadata(
        Platform.linux,
        ['run-daemon'],
        service_paths,
    )

    result = controller.install(daemon_metadata)

    assert result.installed
    assert controller.paths.service == tmp_path / '.config/systemd/user/lyte.service'
    assert runner.commands == [
        ['systemctl', '--user', 'daemon-reload'],
        ['systemctl', '--user', 'enable', 'lyte.service'],
        ['systemctl', '--user', 'start', 'lyte.service'],
    ]


def test_macos_controller_installs_launch_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = FakeRunner()
    monkeypatch.setattr(service, '_uid', lambda: 501)
    controller = ServiceController(Platform.macos, tmp_path, runner)
    daemon_metadata = metadata(Platform.macos, ['--include', 'Mic'])

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
    daemon_metadata = metadata(Platform.linux, ['--include', 'Mic'])

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
    assert runner.commands == [['systemctl', '--user', 'is-active', 'recs.service']]


def test_status_reports_gui_ipc_errors(tmp_path: Path) -> None:
    controller = ServiceController(Platform.linux, tmp_path, FakeRunner())
    controller.paths.status.parent.mkdir(parents=True)
    controller.paths.status.write_text(
        DaemonStatus(recording=True, gui_ipc_error='address in use').model_dump_json()
    )

    result = controller.status()

    assert result.details == 'active\nGUI IPC error: address in use'
    assert result.health is not None
    assert result.health.gui_ipc_error == 'address in use'
