from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def use_temporary_working_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
