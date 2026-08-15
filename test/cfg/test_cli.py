import importlib
import json
import subprocess as sp
from typing import Any

import pytest
import tomli
import tyro

from recs.base.types import Format, SdType, Subtype
from recs.cfg import cli, run_cli


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


def test_option_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed: dict[str, Any] = {}

    def make_cfg(**kwargs: Any) -> dict[str, Any]:
        parsed.update(kwargs)
        return parsed

    def consume(cfg: Any) -> None:
        pass

    monkeypatch.setattr(cli.cfg, 'Cfg', make_cfg)
    monkeypatch.setattr(run_cli, 'run_cli', consume)

    tyro.cli(
        cli.recs,
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
        ],
    )

    assert parsed['alias'] == ['speaker=usb', 'mic']
    assert parsed['formats'] == [Format.wav]
    assert parsed['sdtype'] == SdType.int16
    assert parsed['longest_file_time'] == 90
    assert parsed['preview_headroom'] == 9
    assert not parsed['band_mode']
    assert parsed['save_settings']


@pytest.mark.parametrize('option', ['-f', '--formats'])
def test_audio_options_ignore_case_and_surrounding_dots(
    monkeypatch: pytest.MonkeyPatch, option: str
) -> None:
    parsed: dict[str, Any] = {}

    monkeypatch.setattr(cli.cfg, 'Cfg', lambda **kwargs: parsed.update(kwargs))
    monkeypatch.setattr(run_cli, 'run_cli', lambda cfg: None)

    tyro.cli(
        cli.recs,
        args=[option, '.FLAC.', '--sdtype', '.INT32.', '--subtype', '.PCM_24.'],
    )

    assert parsed['formats'] == [Format.flac]
    assert parsed['sdtype'] == SdType.int32
    assert parsed['subtype'] == Subtype.pcm_24
