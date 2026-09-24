import subprocess
import sys
from pathlib import Path


def test_fix_flac_updates_only_session_files(tmp_path: Path) -> None:
    session = tmp_path / 'results' / 'project' / '2026' / '09' / '24' / '12-00-00'
    session.mkdir(parents=True)
    journal = session / 'session-record.jsonl'
    recording = session / 'recording.toml'
    audio = session / 'audio.wav'
    unrelated = session / 'notes.txt'
    journal.write_text('{"path":"audio.wav"}\n')
    recording.write_text('path = "audio.wav"\n')
    audio.write_text('audio.wav')
    unrelated.write_text('audio.wav')

    subprocess.run(
        [sys.executable, str(Path(__file__).parents[1] / 'scripts/fix-flac.py')],
        cwd=tmp_path,
        check=True,
    )

    assert journal.read_text() == '{"path":"audio.flac"}\n'
    assert recording.read_text() == 'path = "audio.flac"\n'
    assert audio.read_text() == 'audio.wav'
    assert unrelated.read_text() == 'audio.wav'
