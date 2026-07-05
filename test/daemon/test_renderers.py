import plistlib
from pathlib import Path

from recs.daemon import paths, renderers
from recs.daemon.models import Platform


def test_daemon_args_adds_silent() -> None:
    assert renderers.daemon_args(['--include', 'Mic']) == [
        '--silent',
        '--include',
        'Mic',
    ]


def test_daemon_args_preserves_existing_silent() -> None:
    assert renderers.daemon_args(['--silent', '--include', 'Mic']) == [
        '--silent',
        '--include',
        'Mic',
    ]


def test_macos_launch_agent() -> None:
    service_paths = paths.service_paths(Platform.macos, Path('/Users/tom'))
    metadata = renderers.metadata(
        Path('/opt/recs/bin/recs'), Platform.macos, ['--include', 'Mic']
    )

    definition = renderers.macos_launch_agent(metadata, service_paths)
    plist = plistlib.loads(definition.content.encode())

    assert definition.path == Path(
        '/Users/tom/Library/LaunchAgents/com.swirly.recs.plist'
    )
    assert plist['Label'] == 'com.swirly.recs'
    assert plist['ProgramArguments'] == [
        '/opt/recs/bin/recs',
        '--silent',
        '--include',
        'Mic',
    ]
    assert plist['RunAtLoad'] is True
    assert plist['KeepAlive'] is True


def test_linux_systemd_unit() -> None:
    service_paths = paths.service_paths(Platform.linux, Path('/home/tom'))
    metadata = renderers.metadata(
        Path('/opt/recs/bin/recs'), Platform.linux, ['--include', 'Mic']
    )

    definition = renderers.linux_systemd_unit(metadata, service_paths)

    assert definition.path == Path('/home/tom/.config/systemd/user/recs.service')
    assert 'ExecStart=/opt/recs/bin/recs --silent --include Mic' in definition.content
    assert 'Restart=always' in definition.content
    assert 'WantedBy=default.target' in definition.content


def test_linux_xdg_autostart() -> None:
    metadata = renderers.metadata(
        Path('/opt/recs/bin/recs'), Platform.linux, ['--include', 'Mic']
    )

    definition = renderers.linux_xdg_autostart(metadata, Path('/home/tom'))

    assert definition.path == Path('/home/tom/.config/autostart/recs.desktop')
    assert 'Type=Application' in definition.content
    assert 'Exec=/opt/recs/bin/recs --silent --include Mic' in definition.content
    assert 'Terminal=false' in definition.content


def test_windows_task_definition() -> None:
    service_paths = paths.service_paths(Platform.windows, Path('C:/Users/tom'))
    metadata = renderers.metadata(
        Path('C:/Tools/recs.exe'), Platform.windows, ['--include', 'Mic Array']
    )

    task = renderers.windows_task(metadata, service_paths)

    assert task.task_name == 'recs'
    assert task.executable == Path('C:/Tools/recs.exe')
    assert task.arguments == ['--silent', '--include', 'Mic Array']
    assert task.argument_string == '--silent --include "Mic Array"'
    assert task.stdout_log.name == 'recs.out.log'
