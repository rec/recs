from io import StringIO

import pytest
from rich.console import Console

from recs.cfg import Cfg
from recs.ui import live


def test_live_display_is_disabled_without_cursor_support(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mock_devices: None,
) -> None:
    monkeypatch.setenv('TERM', 'xterm-256color')
    monkeypatch.setattr(
        live,
        'CONSOLE',
        Console(file=StringIO(), force_terminal=False),
    )

    display = live.Live(lambda: iter(()), Cfg())

    assert not display.enabled
    assert capsys.readouterr() == (
        '',
        "WARNING: Terminal does not support the live display "
        "(TERM='xterm-256color')\n",
    )


@pytest.mark.parametrize('term', ['emacs', 'unrecognized'])
def test_live_display_is_disabled_for_unrecognized_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mock_devices: None,
    term: str,
) -> None:
    monkeypatch.setenv('TERM', term)
    monkeypatch.setattr(
        live,
        'CONSOLE',
        Console(file=StringIO(), force_terminal=True),
    )

    display = live.Live(lambda: iter(()), Cfg())

    assert not display.enabled
    assert capsys.readouterr() == (
        '',
        f"WARNING: Terminal does not support the live display (TERM='{term}')\n",
    )


def test_live_display_is_enabled_for_supported_terminal(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mock_devices: None,
) -> None:
    monkeypatch.setenv('TERM', 'xterm-256color')
    monkeypatch.setattr(
        live,
        'CONSOLE',
        Console(file=StringIO(), force_terminal=True),
    )

    display = live.Live(lambda: iter(()), Cfg())

    assert display.enabled
    assert capsys.readouterr() == ('', '')
