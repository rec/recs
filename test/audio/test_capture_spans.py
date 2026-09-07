from pathlib import Path

import numpy as np
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.base.types import Format
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.time_settings import TimeSettings
from recs.cfg.track import Track
from recs.model.recording import AudioStream
from recs.recording.migrate import prepare_migration
from recs.ui.recording_session import RecordingSession
from recs.ui.source_recorder import SourceFileEvents


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
    document, _ = prepare_migration(journal)
    stream = document.body.streams[0]
    assert isinstance(stream, AudioStream)
    assert stream.unmapped_fragments == []
    assert sum(f.count for f in stream.fragments) == len(samples)
    assert [(g.start, g.end) for g in stream.gaps] == [(48000, 144000)]
    restored = np.zeros((240000, 1))
    for span in spans:
        restored[span.start : span.start + span.count] = samples[
            span.asset_start : span.asset_start + span.count
        ]
    soundfile.write(tmp_path / 'restored.wav', restored, 48000, subtype='DOUBLE')
    actual, _ = soundfile.read(tmp_path / 'restored.wav')
    np.testing.assert_allclose(
        actual, np.concatenate([tone, np.zeros(144000), tone]), atol=1e-7
    )
