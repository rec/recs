from io import StringIO

import pytest

from recs.ui import gui_child


def test_stdin_rows_ignores_malformed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = gui_child.StdinRows()
    monkeypatch.setattr(
        gui_child.sys,
        'stdin',
        StringIO('not json\n"not rows"\n[{"time":1}]\n'),
    )

    provider._read()

    assert list(provider.rows()) == [{'time': 1}]
    assert provider.closed
