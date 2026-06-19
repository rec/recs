import importlib
import json
import subprocess as sp
import typing as t

import pytest
import tomli
import tyro

from recs.base.types import Format, SdType
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


def test_option_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    parsed: dict[str, t.Any] = {}

    def make_cfg(**kwargs: t.Any) -> dict[str, t.Any]:
        parsed.update(kwargs)
        return parsed

    def consume(cfg: t.Any) -> None:
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
            '--no-band-mode',
        ],
    )

    assert parsed['alias'] == ['speaker=usb', 'mic']
    assert parsed['formats'] == [Format.wav]
    assert parsed['sdtype'] == SdType.int16
    assert parsed['longest_file_time'] == 90
    assert not parsed['band_mode']
