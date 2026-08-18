import plistlib
import sys
from pathlib import Path

from reccy.models import Platform, ServiceSpec

from recs.daemon import paths, renderers


def test_daemon_args_adds_silent() -> None:
    assert renderers.daemon_args(['--include', 'Mic']) == [
        '-m',
        'recs',
        '--silent',
        '--include',
        'Mic',
    ]


def test_daemon_args_preserves_existing_silent() -> None:
    assert renderers.daemon_args(['--silent', '--include', 'Mic']) == [
        '-m',
        'recs',
        '--silent',
        '--include',
        'Mic',
    ]


def test_macos_launch_agent() -> None:
    service_paths = paths.service_paths(Platform.macos, Path('/Users/tom'))
    metadata = renderers.metadata(Platform.macos, ['--include', 'Mic'])

    definition = renderers.macos_launch_agent(metadata, service_paths)
    plist = plistlib.loads(definition.content.encode())

    assert definition.path == Path(
        '/Users/tom/Library/LaunchAgents/com.swirly.recs.plist'
    )
    assert plist['Label'] == 'com.swirly.recs'
    assert plist['ProgramArguments'] == [
        sys.executable,
        '-m',
        'recs',
        '--silent',
        '--include',
        'Mic',
    ]
    assert plist['EnvironmentVariables'] == {
        'RECCY_LOG_PATH': '/Users/tom/Library/Logs/recs/recs.log',
        'RECS_DAEMON': '1',
    }
    assert plist['RunAtLoad'] is True
    assert plist['KeepAlive'] is True


def test_paths_support_custom_service_identity() -> None:
    service = ServiceSpec(
        name='lyte',
        display_name='lyte',
        description='lyte lighting daemon',
        launchd_label='com.swirly.lyte',
        daemon_env_var='LYTE_DAEMON',
        windows_pipe=r'\\.\pipe\lyte',
    )

    linux = paths.service_paths(Platform.linux, Path('/home/tom'), service)
    macos = paths.service_paths(Platform.macos, Path('/Users/tom'), service)
    windows = paths.service_paths(Platform.windows, Path('C:/Users/tom'), service)

    assert linux.metadata == Path('/home/tom/.config/lyte/daemon.json')
    assert linux.service == Path('/home/tom/.config/systemd/user/lyte.service')
    assert linux.gui_endpoint == Path('/home/tom/.local/state/lyte/gui.sock')
    assert macos.service == Path(
        '/Users/tom/Library/LaunchAgents/com.swirly.lyte.plist'
    )
    assert windows.gui_endpoint == r'\\.\pipe\lyte'


def test_external_ipc_paths_use_platform_endpoints() -> None:
    home = Path('/home/tom')

    assert paths.external_control_endpoint(home, Platform.linux) == (
        home / '.local/state/recs/control.sock'
    )
    assert paths.external_event_endpoint(home, Platform.linux) == (
        home / '.local/state/recs/events.sock'
    )
    assert paths.external_control_endpoint(home, Platform.windows) == (
        r'\\.\pipe\recs-control'
    )
    assert paths.external_event_endpoint(home, Platform.windows) == (
        r'\\.\pipe\recs-events'
    )


def test_linux_systemd_unit() -> None:
    service_paths = paths.service_paths(Platform.linux, Path('/home/tom'))
    metadata = renderers.metadata(Platform.linux, ['--include', 'Mic'])

    definition = renderers.linux_systemd_unit(metadata, service_paths)

    assert definition.path == Path('/home/tom/.config/systemd/user/recs.service')
    assert f'ExecStart={sys.executable} -m recs --silent --include Mic' in (
        definition.content
    )
    assert 'Environment=RECS_DAEMON=1' in definition.content
    assert 'Environment=RECCY_LOG_PATH=/home/tom/.local/state/recs/recs.log' in (
        definition.content
    )
    assert 'Restart=always' in definition.content
    assert 'WantedBy=default.target' in definition.content


def test_linux_systemd_unit_supports_custom_service_identity() -> None:
    service = ServiceSpec(
        name='lyte',
        display_name='lyte',
        description='lyte lighting daemon',
        launchd_label='com.swirly.lyte',
        daemon_env_var='LYTE_DAEMON',
        windows_pipe=r'\\.\pipe\lyte',
    )
    service_paths = paths.service_paths(Platform.linux, Path('/home/tom'), service)
    metadata = renderers.service_metadata(
        Platform.linux,
        ['-m', 'lyte', 'run-daemon'],
        service_paths,
    )

    definition = renderers.linux_systemd_unit(metadata, service_paths, service)

    assert definition.path == Path('/home/tom/.config/systemd/user/lyte.service')
    assert 'Description=lyte lighting daemon' in definition.content
    assert f'ExecStart={sys.executable} -m lyte run-daemon' in definition.content
    assert 'Environment=LYTE_DAEMON=1' in definition.content
    assert 'Environment=RECCY_LOG_PATH=/home/tom/.local/state/lyte/lyte.log' in (
        definition.content
    )


def test_linux_xdg_autostart() -> None:
    metadata = renderers.metadata(Platform.linux, ['--include', 'Mic'])

    definition = renderers.linux_xdg_autostart(metadata, Path('/home/tom'))

    assert definition.path == Path('/home/tom/.config/autostart/recs.desktop')
    assert 'Type=Application' in definition.content
    assert f'Exec={sys.executable} -m recs --silent --include Mic' in definition.content
    assert 'Terminal=false' in definition.content


def test_windows_task_definition() -> None:
    service_paths = paths.service_paths(Platform.windows, Path('C:/Users/tom'))
    metadata = renderers.metadata(Platform.windows, ['--include', 'Mic Array'])

    task = renderers.windows_task(metadata, service_paths)

    assert task.task_name == 'recs'
    assert task.arguments == [
        '-m',
        'reccy.service_runner',
        'C:/Users/tom/AppData/Local/recs/logs/recs.log',
        '-m',
        'recs',
        '--silent',
        '--include',
        'Mic Array',
    ]
    assert task.log.name == 'recs.log'
