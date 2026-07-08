import sys

import pytest

from recs.base import app_command


def test_app_command_uses_module_when_not_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(sys, 'frozen', raising=False)

    assert app_command.command('gui-child') == [
        sys.executable,
        '-m',
        'recs',
        'gui-child',
    ]


def test_app_command_uses_executable_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'frozen', True, raising=False)

    assert app_command.command('gui-child') == [sys.executable, 'gui-child']
