import json
from pathlib import Path

import pytest

from recs.ui import session_manifest
from recs.ui.session_manifest import ManifestEvent, ManifestFile, SessionManifestWriter


def test_session_manifest_writer_fsyncs_every_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fsynced: list[int] = []
    monkeypatch.setattr(session_manifest.os, 'fsync', fsynced.append)
    writer = SessionManifestWriter(tmp_path / 'recs-session.jsonl', started_at='start')

    writer.write(
        ManifestEvent(timestamp='event', type='key_pressed', key='g'),
    )
    writer.close()

    lines = (tmp_path / 'recs-session.jsonl').read_text().splitlines()
    assert [json.loads(line)['type'] for line in lines] == ['header', 'key_pressed']
    assert len(fsynced) == 2


def test_session_manifest_reader_ignores_truncated_final_line(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"key_pressed","timestamp":"event","key":"g"}\n'
        '{"type":'
    )

    result = session_manifest.read(manifest)

    assert result.started_at == 'start'
    assert result.events == [
        ManifestEvent(timestamp='event', type='key_pressed', key='g')
    ]
    assert 'truncated final line' in result.errors[0]


def test_session_manifest_reader_keeps_file_lifecycle(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"file_started","timestamp":"start","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"file_finished","timestamp":"end","path":"take.wav",'
        '"track":1,"channels":1,"sample_rate":48000,"bit_depth":32}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    result = session_manifest.read(manifest)

    assert result.files == [
        ManifestFile(
            type='file_started',
            timestamp='start',
            path='take.wav',
            track=1,
            channels=1,
            sample_rate=48_000,
            bit_depth=32,
        ),
        ManifestFile(
            type='file_finished',
            timestamp='end',
            path='take.wav',
            track=1,
            channels=1,
            sample_rate=48_000,
            bit_depth=32,
        ),
    ]
    assert result.ended_at == 'end'
    assert result.duration == 1
