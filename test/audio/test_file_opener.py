from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest
import soundfile
from ufor.encoding import Format

from recs.audio.file_opener import FileOpener


@pytest.mark.parametrize('name', ['take', 'take.wav', 'take.flac'])
def test_collisions_preserve_existing_audio_and_increment_before_the_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    samples = np.full(48_000, 0.25, dtype=np.float32)
    existing = [tmp_path / 'take.wav', tmp_path / 'take_1.wav']
    for path in existing:
        soundfile.write(path, samples, 48_000)
    originals = {p: p.read_bytes() for p in existing}
    attempted: set[Path] = set()
    original_open = FileOpener.open

    def checked_open(
        self: FileOpener,
        path: Path | str,
        metadata: Mapping[str, str],
        overwrite: bool = False,
    ) -> soundfile.SoundFile:
        output = Path(path).with_suffix('.' + self.format)
        # Fail promptly if retries target the same file instead of hanging.
        assert output not in attempted
        attempted.add(output)
        return original_open(self, path, metadata, overwrite)

    monkeypatch.setattr(FileOpener, 'open', checked_open)
    with FileOpener(format=Format.wav).create({}, tmp_path / name) as output:
        assert Path(output.name) == tmp_path / 'take_2.wav'
        output.write(samples)

    for path, content in originals.items():
        assert path.read_bytes() == content
    data, rate = soundfile.read(tmp_path / 'take_2.wav')
    assert rate == 48_000
    np.testing.assert_array_equal(data, samples)
