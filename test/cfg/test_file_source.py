from pathlib import Path

import pytest
import soundfile

from recs.base.errors import RecsError
from recs.cfg.file_source import FileSource


def test_missing_audio_input_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / 'missing.wav'

    with pytest.raises(RecsError, match='Cannot read audio input') as result:
        FileSource(path)

    assert str(path) in str(result.value)


def test_malformed_audio_input_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / 'broken.wav'
    path.write_text('not an audio file')

    with pytest.raises(RecsError, match='Cannot read audio input') as result:
        FileSource(path)

    assert str(path) in str(result.value)


def test_unreadable_audio_input_reports_a_user_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / 'blocked.wav'

    def fail_open(*, file: Path, mode: str) -> soundfile.SoundFile:
        raise PermissionError('access denied')

    monkeypatch.setattr(soundfile, 'SoundFile', fail_open)

    with pytest.raises(RecsError, match='access denied') as result:
        FileSource(path)

    assert str(path) in str(result.value)
