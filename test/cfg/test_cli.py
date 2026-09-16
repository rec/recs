import importlib
import json
import subprocess as sp
import sys
import tomllib

import pytest
import tyro
from reccy.pytest_plugin import CliHelp
from ufor.encoding import Format, Subtype

from recs.__main__ import run
from recs.base.types import MidiTiming, SdType
from recs.cfg import cli
from recs.edit import commands
from recs.recording import session_browser


def test_console_script_entry_point() -> None:
    project = tomllib.loads(open('pyproject.toml').read())['project']
    module_name, function_name = project['scripts']['recs'].split(':')

    module = importlib.import_module(module_name)

    assert callable(getattr(module, function_name))


def test_info():
    cmd = 'python -m recs --info'
    r = sp.run(cmd, text=True, check=True, stdout=sp.PIPE, shell=True).stdout
    json.loads(r)


def test_help(cli_help: CliHelp) -> None:
    cli_help(
        'recs',
        run,
        subcommands=[
            'daemon',
            'preflight',
            'readiness',
            'control',
            'watch',
            'profile',
            'sessions',
            'session',
            'test-input',
            'explain',
            'record',
            'edit',
        ],
    )


@pytest.mark.parametrize(
    ('group', 'commands'),
    [
        (
            'session',
            [
                'show',
                'quality',
                'markers',
                'extract',
                'handoff',
                'recover',
                'finalize',
                'export-midi',
                'migrate',
                'export',
            ],
        ),
        ('record', ['check']),
        ('profile', ['save', 'use', 'show', 'list', 'delete']),
        ('daemon', ['install', 'uninstall', 'start', 'stop', 'restart', 'status']),
        (
            'control',
            [
                'instances',
                'status',
                'disk',
                'devices',
                'capabilities',
                'mutable',
                'get',
                'set',
                'mark',
                'pause',
                'play',
                'stop',
                'pause-playback',
                'continue',
                'jump',
                'jump-session',
                'resume',
                'calibrate',
                'card-replace',
                'reload-profiles',
            ],
        ),
        ('edit', ['compose']),
    ],
    ids=['session', 'record', 'profile', 'daemon', 'control', 'edit'],
)
def test_command_group_help(cli_help: CliHelp, group: str, commands: list[str]) -> None:
    def invoke() -> int:
        sys.argv = ['recs', group, *sys.argv[1:]]
        return run()

    cli_help(f'recs {group}', invoke, subcommands=commands)


@pytest.mark.parametrize(
    'command',
    [
        ['sessions'],
        ['session'],
        ['session', 'show'],
        ['session', 'quality'],
        ['session', 'markers'],
        ['session', 'extract'],
        ['session', 'handoff'],
        ['session', 'recover'],
        ['session', 'export'],
        ['record'],
        ['record', 'check'],
        ['edit'],
        ['edit', 'compose'],
        ['query-devices'],
        ['query-devices-stream'],
        ['explain'],
        ['daemon', 'install'],
        ['daemon', 'start'],
        ['daemon', 'stop'],
        ['daemon', 'restart'],
        ['daemon', 'uninstall'],
        ['daemon', 'status'],
        ['control', 'instances'],
    ],
)
def test_help_exits_before_discovery_or_execution(
    monkeypatch: pytest.MonkeyPatch, command: list[str]
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail('Help must not discover recordings, recipes, or devices')

    monkeypatch.setattr(session_browser, 'scan', unexpected)
    monkeypatch.setattr(session_browser, 'summarize', unexpected)
    monkeypatch.setattr('recs.recording.session_quality.inspect', unexpected)
    monkeypatch.setattr('recs.recording.markers.read_markers', unexpected)
    monkeypatch.setattr('recs.edit.marker_extract.plan_extraction', unexpected)
    monkeypatch.setattr('recs.edit.track_handoff.plan_handoff', unexpected)
    monkeypatch.setattr('recs.recording.session_recovery.inspect_recovery', unexpected)
    monkeypatch.setattr('recs.recording.session_export.export', unexpected)
    monkeypatch.setattr(commands, 'resolve_command', unexpected)
    monkeypatch.setattr('recs.__main__.devices_json', unexpected)
    monkeypatch.setattr('recs.__main__.stream_devices', unexpected)
    monkeypatch.setattr('recs.recording.session_explain.explain', unexpected)
    monkeypatch.setattr('recs.recording.session_explain.explain_daemon', unexpected)
    monkeypatch.setattr('recs.daemon.cli.ServiceController', unexpected)
    monkeypatch.setattr('recs.daemon.control_cli.instances.list_instances', unexpected)
    monkeypatch.setattr(sys, 'argv', ['recs', *command, '--help'])

    with pytest.raises(SystemExit) as result:
        run()

    assert result.value.code == 0


@pytest.mark.parametrize('argument', ['shwo', '/existing/session'])
def test_unknown_session_command_is_not_a_directory_scan(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    monkeypatch.setattr(
        session_browser, 'scan', lambda root: pytest.fail('Unexpected directory scan')
    )
    monkeypatch.setattr(sys, 'argv', ['recs', 'session', argument])

    with pytest.raises(SystemExit) as result:
        run()

    assert result.value.code == 2


def test_option_parsing() -> None:
    parsed = tyro.cli(
        cli.CliCfg,
        args=[
            '-a',
            'speaker=usb',
            '-a',
            'mic',
            '-f',
            'wa',
            '-d',
            'int1',
            '--longest-file-time',
            '1:30',
            '--preview-headroom',
            '9',
            '--no-band-mode',
            '--save-settings',
            'True',
            '--midi-include',
            'Launchkey',
            '--midi-exclude',
            'Network',
            '--midi-timing',
            'system',
            '--waveform-bucket-milliseconds',
            '10',
            '--waveform-batch-milliseconds',
            '40',
        ],
    )

    assert parsed.device.alias == ['speaker=usb', 'mic']
    assert parsed.audio.formats == [Format.wav]
    assert parsed.audio.sdtype == SdType.int16
    assert parsed.recording.longest_file_time == 90
    assert parsed.recording.preview_headroom == 9
    assert not parsed.recording.band_mode
    assert parsed.general.save_settings
    assert parsed.midi.midi_include == ['Launchkey']
    assert parsed.midi.midi_exclude == ['Network']
    assert parsed.midi.midi_timing == MidiTiming.system
    assert parsed.console.waveform_bucket_milliseconds == 10
    assert parsed.console.waveform_batch_milliseconds == 40


@pytest.mark.parametrize('option', ['-f', '--formats'])
def test_audio_options_ignore_case_and_surrounding_dots(
    option: str,
) -> None:
    parsed = tyro.cli(
        cli.CliCfg,
        args=[option, '.FLAC.', '--sdtype', '.INT32.', '--subtype', '.PCM_24.'],
    )

    assert parsed.audio.formats == [Format.flac]
    assert parsed.audio.sdtype == SdType.int32
    assert parsed.audio.subtype == Subtype.pcm_24
