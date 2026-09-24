import subprocess
import sys
from pathlib import Path


def test_rename_result_files_updates_matching_media_and_session_references(
    tmp_path: Path,
) -> None:
    session = tmp_path / 'results' / 'project' / '2025' / '09' / '13' / '20-06-12'
    audio = session / 'audio'
    audio.mkdir(parents=True)
    old_names = [
        'FLOW 8 (Recording) + 9-10 + 20250831-175707.flac',
        'LiveTrak L-12 master + MASTER + 20250913-200612.flac',
        'LiveTrak L-12 + TRACK09_10 + 20250913-200612.flac',
        'LiveTrak L-12 + TRACK05 + 20251123-194828.flac',
        'FLOW 8 + 5-6 + 20260328-143842.flac',
        'LiveTrak L-12 + TRACK03 + 20170101-013950.WAV',
        'LiveTrak L-12 + TRACK09_10 + 20170101-013950.WAV',
    ]
    new_names = [
        '9-10 + 20250831-175707.flac',
        'master + 20250913-200612.flac',
        '9-10 + 20250913-200612.flac',
        '5 + 20251123-194828.flac',
        '5-6 + 20260328-143842.flac',
        '3 + 20170101-013950.WAV',
        '9-10 + 20170101-013950.WAV',
    ]
    for name in old_names:
        (audio / name).write_text(name)
    untouched = audio / 'LiveTrak L-12 legacy.flac'
    untouched.write_text('untouched')
    (audio / 'MacBook Pro + 1 + 20250913-200612.flac').write_text('untouched')
    old_paths = '\n'.join(f'path = "audio/{name}"' for name in old_names)
    old_wav_path = old_names[0].removesuffix('.flac') + '.wav'
    old_upper_wav_path = old_names[-1]
    recording = session / 'recording.toml'
    recording.write_text(
        f'{old_paths}\npath = "audio/{old_wav_path}"\n'
        f'path = "audio/{old_upper_wav_path}"\n'
    )
    journal = session / 'session-record.jsonl'
    journal.write_text(
        '\n'.join(f'{{"path":"audio/{name}"}}' for name in old_names)
        + f'\n{{"path":"audio/{old_wav_path}"}}\n'
        + f'{{"path":"audio/{old_upper_wav_path}"}}\n'
    )

    command = [
        sys.executable,
        str(Path(__file__).parents[1] / 'scripts/rename-result-files.py'),
    ]
    dry_run = subprocess.run(
        [*command, '--dry-run'],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    for old, new in zip(old_names, new_names, strict=True):
        assert (audio / old).read_text() == old
        assert old in dry_run.stdout
        assert new in dry_run.stdout
    assert str(recording.relative_to(tmp_path)) in dry_run.stdout
    assert str(journal.relative_to(tmp_path)) in dry_run.stdout
    assert 'Remaining files containing LiveTrak: 1' in dry_run.stdout
    assert 'Remaining files containing MacBook: 1' in dry_run.stdout
    assert 'Remaining files containing FLOW: 0' in dry_run.stdout

    result = subprocess.run(
        command,
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    for old, new in zip(old_names, new_names, strict=True):
        assert not (audio / old).exists()
        assert (audio / new).read_text() == old
        assert f'audio/{new}' in recording.read_text()
        assert f'audio/{new}' in journal.read_text()
        assert old in result.stdout
        assert new in result.stdout
    assert 'Remaining files containing LiveTrak: 1' in result.stdout
    assert 'Remaining files containing MacBook: 1' in result.stdout
    assert 'Remaining files containing FLOW: 0' in result.stdout
    assert f'audio/{old_wav_path}' not in recording.read_text()
    assert f'audio/{old_wav_path}' not in journal.read_text()
    assert f'audio/{old_upper_wav_path}' not in recording.read_text()
    assert f'audio/{old_upper_wav_path}' not in journal.read_text()
    assert untouched.read_text() == 'untouched'
