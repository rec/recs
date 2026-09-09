from pathlib import Path

import numpy as np
import soundfile
from ufor.interface import NormalizeMode

from recs.edit.schema import parse_edit
from recs.edit.session import execute_edit, prepare_edit
from recs.recording.finalize import finalize_recording
from recs.recording.read import read_recording
from recs.ui import session_record


def test_edit_creates_audio_canonical_edit_and_session_record(tmp_path: Path) -> None:
    source_directory = tmp_path / 'source'
    source_directory.mkdir()
    audio = np.linspace(-0.5, 0.5, 48_000, dtype=np.float32)[:, np.newaxis]
    source_path = source_directory / 'take.wav'
    soundfile.write(source_path, audio, 48_000, subtype='FLOAT')
    record_path = source_directory / 'recording.toml'
    writer = session_record.SessionRecordWriter(
        (record_path).with_name('session-record.jsonl'),
        started_at='start',
        session_id='input-session',
    )
    values = {
        'media_type': 'audio',
        'stream_id': 'audio:device:1',
        'format': 'wav',
        'path': 'take.wav',
        'source': 'device',
        'track_name': 'voice',
        'source_channels': [1],
        'channels': 1,
        'sample_rate': 48_000,
        'bit_depth': 32,
    }
    writer.write(
        session_record.AudioFileRecord(
            clock_id='audio',
            type='file_started',
            timestamp='start',
            frame_count=0,
            **values,
        )
    )
    writer.write(
        session_record.AudioFileRecord(
            clock_id='audio',
            type='file_finished',
            timestamp='end',
            frame_count=48_000,
            quantity_count=48_000,
            **values,
        )
    )
    writer.write(session_record.SessionFooter(ended_at='end', duration_seconds=1))
    writer.close()
    finalize_recording(writer.path)
    edit = parse_edit(
        """
format = "recs"
version = 2
kind = "arrangement"
id = "edit"
name = "Audio edit"

[[timebases]]
id = "audio"

[timebases.rate]
numerator = 48000
denominator = 1

[body]
timebase = "audio"

[[body.tracks]]
id = "voice"

[body.tracks.stream]
timebase = "audio"
channels = ["channel-0"]

[[body.clips]]
id = "voice-clip"
track = "voice"
source_start = 0
source_end = 48000
timeline_start = 0

[body.clips.source]
node = "voice-source"
port = "audio"

[[body.nodes]]
id = "voice-source"

[body.nodes.definition]
path = "recording.toml"

[[destinations]]
port = "voice"
path = "audio/voice.wav"
format = "wav"
subtype = "float"

[[ports]]
id = "voice"
direction = "output"

[ports.stream]
timebase = "audio"
channels = ["channel-0"]

[ports.binding]
track = "voice"
"""
    )
    source_document = read_recording(record_path)
    raw = edit.model_dump()
    raw['body']['clips'][0]['source']['port'] = source_document.ports[0].id
    raw['body']['tracks'][0]['stream'] = source_document.ports[0].stream.model_dump()
    raw['ports'][0]['stream'] = source_document.ports[0].stream.model_dump()
    edit = type(edit).model_validate(raw)
    destination = tmp_path / 'edited'

    prepared = prepare_edit(edit, source_directory, destination)

    assert not destination.exists()
    assert prepared.edit.body.nodes[0].definition.path == '../source/recording.toml'

    output_record = execute_edit(edit, source_directory, destination)

    rendered, sample_rate = soundfile.read(
        destination / 'audio/voice.wav', dtype='float32', always_2d=True
    )
    np.testing.assert_array_equal(rendered, audio)
    assert sample_rate == 48_000
    assert (destination / 'edit.toml').is_file()
    result = session_record.read(output_record.with_name('session-record.jsonl'))
    assert result.application == {'name': 'recs edit'}
    assert [f.type for f in result.files] == ['file_started', 'file_finished']
    assert result.files[-1].source == 'edit'
    assert result.files[-1].track_name == 'voice'
    assert result.files[-1].source_channels == [1]
    assert result.files[-1].quantity_count == 48_000
    assert result.ended_at is not None
    assert result.events[0].metadata == {
        'sources': {
            f'root/voice-source/{source_document.ports[0].id}': {
                'session_id': 'input-session',
                'files': [source_path.as_posix()],
            }
        },
        'output_ranges': {'voice': {'start': 0, 'end': 48_000}},
    }

    chained_destination = tmp_path / 'chained'
    exported = read_recording(destination / 'recording.toml')
    raw = edit.model_dump()
    raw['body']['nodes'][0]['definition']['path'] = 'recording.toml'
    raw['body']['clips'][0]['source']['port'] = exported.ports[0].id
    raw['body']['tracks'][0]['stream'] = exported.ports[0].stream.model_dump()
    raw['ports'][0]['stream'] = exported.ports[0].stream.model_dump()
    chained = type(edit).model_validate(raw)

    execute_edit(chained, destination, chained_destination)

    chained_audio, chained_rate = soundfile.read(
        chained_destination / 'audio/voice.wav', dtype='float32', always_2d=True
    )
    np.testing.assert_array_equal(chained_audio, audio)
    assert chained_rate == 48_000

    normalized_destination = tmp_path / 'normalized'
    raw = edit.model_dump()
    raw['ports'][0]['binding']['normalize'] = NormalizeMode.normalize
    normalized = type(edit).model_validate(raw)

    execute_edit(normalized, source_directory, normalized_destination)

    normalized_audio, normalized_rate = soundfile.read(
        normalized_destination / 'audio/voice.wav',
        dtype='float32',
        always_2d=True,
    )
    assert normalized_rate == 48_000
    assert np.max(np.abs(normalized_audio)) == 1
