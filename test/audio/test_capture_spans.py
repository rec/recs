import json
from pathlib import Path

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from ufor.encoding import Format
from ufor.recording import AudioStream
from ufor.references import RecordSelector

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.time_settings import TimeSettings
from recs.cfg.track import Track
from recs.edit.inputs import SourceSpec
from recs.edit.materialized import materialize_source
from recs.edit.record import resolve_input
from recs.recording import session_record
from recs.recording.capture_events import SourceFileEvents, capture_clock_id
from recs.recording.finalize import prepare_recording
from recs.recording.recording_session import RecordingSession


def test_level_trigger_frame_is_recorded_with_preroll(tmp_path: Path) -> None:
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48000, 'max_input_channels': 1}
    )
    writer = ChannelWriter(
        Cfg(formats=[Format.wav], output_directory=str(tmp_path)),
        TimeSettings[int](quiet_before_start=48000, stop_after_quiet=480000),
        Track(source, '1'),
    )
    quiet = np.zeros(48000, dtype=np.float32)
    loud = np.tile(np.array([-0.5, 0.5], dtype=np.float32), 24000)
    writer.receive_update(
        Block(block=quiet), 1.0, should_record=False, timeline_frame=48000
    )
    writer.receive_update(
        Block(block=loud), 2.0, should_record=True, timeline_frame=96000
    )
    writer.stop()

    events = SourceFileEvents([writer])
    paths, records = events.new_files([writer], 32)
    assert len(records) == 1
    assert records[0].start_frame == 0
    assert records[0].trigger_frame == 48000

    session = RecordingSession('test', 0.0)
    journal = tmp_path / 'session-record.jsonl'
    session.start(journal, enabled=True)
    session.record_file_started(records[0], None)
    session.record_files(
        paths,
        events.end_frames([writer]),
        events.end_timestamps([writer]),
        events.spans([writer]),
    )
    session.record_file_finished(paths[0])
    session.finish(2.0)
    assert [f.trigger_frame for f in session_record.read(journal).files] == [
        48000,
        48000,
    ]


@pytest.mark.parametrize('record_everything', [False, True])
def test_non_level_starts_have_no_trigger_frame(
    tmp_path: Path, record_everything: bool
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48000, 'max_input_channels': 1}
    )
    writer = ChannelWriter(
        Cfg(formats=[Format.wav], output_directory=str(tmp_path)),
        TimeSettings[int](record_everything=record_everything),
        Track(source, '1'),
    )
    block = np.tile(np.array([-0.5, 0.5], dtype=np.float32), 24000)
    if not record_everything:
        block = np.zeros(48000, dtype=np.float32)
    writer.receive_update(
        Block(block=block), 1.0, should_record=True, timeline_frame=48000
    )
    writer.stop()

    _, records = SourceFileEvents([writer]).new_files([writer], 32)
    assert len(records) == 1
    assert records[0].trigger_frame is None
    session = RecordingSession('test', 0.0)
    journal = tmp_path / 'session-record.jsonl'
    session.start(journal, enabled=True)
    session.record_file_started(records[0], None)
    session.finish(1.0)
    started = next(
        json.loads(line)
        for line in journal.read_text().splitlines()
        if '"file_started"' in line
    )
    assert 'trigger_frame' not in started


def test_file_split_has_no_new_trigger_frame(tmp_path: Path) -> None:
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48000, 'max_input_channels': 1}
    )
    writer = ChannelWriter(
        Cfg(formats=[Format.wav], output_directory=str(tmp_path)),
        TimeSettings[int](longest_file_time=48000),
        Track(source, '1'),
    )
    block = Block(block=np.tile(np.array([-0.5, 0.5], dtype=np.float32), 24000))
    writer.receive_update(block, 1.0, timeline_frame=48000)
    writer.receive_update(block, 2.0, timeline_frame=96000)
    writer.stop()

    _, records = SourceFileEvents([writer]).new_files([writer], 32)
    assert [r.trigger_frame for r in records] == [0, None]


def test_silence_trimming_preserves_exact_asset_and_timeline_ranges(
    tmp_path: Path,
    data_regression: DataRegressionFixture,
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48000, 'max_input_channels': 1}
    )
    cfg = Cfg(formats=[Format.wav], output_directory=str(tmp_path))
    writer = ChannelWriter(
        cfg,
        TimeSettings[int](
            quiet_before_start=0,
            quiet_after_end=48000,
            stop_after_quiet=480000,
            shortest_file_time=1,
        ),
        Track(source, '1'),
    )
    tone = np.sin(np.arange(48000) * (2 * np.pi * 440 / 48000)) * 0.25
    for index in range(5):
        writer.receive_update(
            Block(block=tone if index in (0, 4) else np.zeros(48000)),
            1700000000.0 + index + 1,
            should_record=index in (0, 4),
            timeline_frame=(index + 1) * 48000,
        )
    writer.stop()
    assert len(writer.files_written) == 1
    path = writer.files_written[0]
    samples, rate = soundfile.read(path, always_2d=True)
    assert rate == 48000
    assert len(samples) == 144000
    spans = writer.file_spans[path]
    data_regression.check([s.model_dump() for s in spans])
    session = RecordingSession('test', 1700000000.0)
    journal = tmp_path / 'session-record.jsonl'
    session.start(journal, enabled=True)
    session.write(
        session_record.EventRecord(
            type='source_online',
            timestamp='observed',
            source=source.name,
            clock_id=capture_clock_id(source.name),
            channel_count=source.channels,
            sample_rate=source.samplerate,
        )
    )
    events = SourceFileEvents([writer])
    paths, records = events.new_files([writer], 32)
    for record in records:
        session.record_file_started(record, 'Mic')
    session.record_files(
        paths,
        events.end_frames([writer]),
        events.end_timestamps([writer]),
        events.spans([writer]),
    )
    session.finish(1700000005.0)
    document, _ = prepare_recording(journal)
    stream = document.body.streams[0]
    assert isinstance(stream, AudioStream)
    assert stream.unmapped_fragments == []
    assert sum(f.count for f in stream.fragments) == len(samples)
    assert [(g.start, g.end) for g in stream.gaps] == [(48000, 144000)]
    edit = SourceSpec(
        name='take',
        record=tmp_path / 'recording.toml',
        selector=RecordSelector(source='Mic', track='1'),
    )
    resolved = resolve_input(edit, tmp_path)
    restored = materialize_source(resolved)
    with soundfile.SoundFile(
        tmp_path / 'restored.wav',
        'w',
        samplerate=48000,
        channels=restored.channels,
        subtype='DOUBLE',
    ) as fp:
        for block in restored.blocks():
            fp.write(block)
    actual, _ = soundfile.read(tmp_path / 'restored.wav')
    np.testing.assert_allclose(
        actual, np.concatenate([tone, np.zeros(144000), tone]), atol=1e-7
    )
