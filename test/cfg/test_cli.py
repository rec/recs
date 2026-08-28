import importlib
import json
import subprocess as sp

import pytest
import tomli
import tyro

from recs.base.types import Format, MidiTiming, SdType, Subtype
from recs.cfg import cli


def test_console_script_entry_point() -> None:
    project = tomli.loads(open('pyproject.toml').read())['project']
    module_name, function_name = project['scripts']['recs'].split(':')

    module = importlib.import_module(module_name)

    assert callable(getattr(module, function_name))


def test_info():
    cmd = 'python -m recs --info'
    r = sp.run(cmd, text=True, check=True, stdout=sp.PIPE, shell=True).stdout
    json.loads(r)


def test_help_has_no_consecutive_empty_lines() -> None:
    cmd = 'python -m recs --help'
    help_text = sp.run(cmd, text=True, check=True, stdout=sp.PIPE, shell=True).stdout
    lines = help_text.splitlines()

    for first, second in zip(lines, lines[1:], strict=False):
        assert first or second


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
