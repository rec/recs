from pathlib import Path

import numpy as np
import soundfile

from recs.edit.record import resolve_sources
from recs.edit.schema import parse_edit
from recs.ui.session_record import FileRecord, SessionFooter, SessionRecordWriter


def test_source_resolution_preserves_gaps_and_selects_mono_offset(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / 'session-record.jsonl'
    writer = SessionRecordWriter(record_path, started_at='start', session_id='session')
    _write_audio_fragment(writer, tmp_path, 'first.wav', 0, 48_000)
    _write_audio_fragment(writer, tmp_path, 'second.wav', 96_000, 144_000)
    writer.write(SessionFooter(ended_at='end', duration_seconds=3))
    writer.close()
    edit = parse_edit(
        """
schema_version = 1
sample_rate = 48000

[[sources]]
id = "right"
record = "session-record.jsonl"
channel = "device:pair:2"
"""
    )

    source = resolve_sources(edit, tmp_path)['right']

    assert source.channels == 1
    assert [(f.start, f.end) for f in source.fragments] == [
        (0, 48_000),
        (96_000, 144_000),
    ]
    assert [f.channel_offset for f in source.fragments] == [1, 1]


def _write_audio_fragment(
    writer: SessionRecordWriter,
    directory: Path,
    name: str,
    start: int,
    end: int,
) -> None:
    path = directory / name
    soundfile.write(path, np.zeros((end - start, 2)), 48_000, subtype='FLOAT')
    values = {
        'media_type': 'audio',
        'stream_id': 'audio:device:1-2',
        'format': 'wav',
        'path': name,
        'source': 'device',
        'track_name': 'pair',
        'source_channels': [1, 2],
        'channels': 2,
        'sample_rate': 48_000,
        'bit_depth': 32,
    }
    writer.write(
        FileRecord(type='file_started', timestamp='start', frame_count=start, **values)
    )
    writer.write(
        FileRecord(
            type='file_finished',
            timestamp='end',
            frame_count=end,
            quantity_count=end - start,
            **values,
        )
    )
