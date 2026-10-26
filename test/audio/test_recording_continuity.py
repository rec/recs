from pathlib import Path

import numpy as np
import pytest
import soundfile

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.time_settings import TimeSettings
from recs.cfg.track import Track
from recs.recording.capture_events import SourceFileEvents


def make_writer(directory: Path, times: TimeSettings[int]) -> ChannelWriter:
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48_000, 'max_input_channels': 1}
    )
    return ChannelWriter(
        Cfg(formats=['wav'], output_directory=str(directory)),
        times,
        Track(source, '1'),
    )


@pytest.mark.parametrize('quiet_seconds', [15, 20, 21])
@pytest.mark.parametrize('stop_seconds', [5, 20])
def test_padding_keeps_touching_performances_continuous(
    tmp_path: Path, quiet_seconds: int, stop_seconds: int
) -> None:
    writer = make_writer(
        tmp_path,
        TimeSettings[int](
            quiet_before_start=480_000,
            quiet_after_end=480_000,
            stop_after_quiet=stop_seconds * 48_000,
        ),
    )
    # Distinct quiet blocks reveal whether the beginning or end was retained.
    samples = [
        np.full(48_000, i / 1000, dtype=np.float32) for i in range(quiet_seconds + 2)
    ]
    try:
        for i, block in enumerate(samples):
            writer.receive_update(
                Block(block=block),
                float(i + 1),
                should_record=i in (0, len(samples) - 1),
                timeline_frame=(i + 1) * 48_000,
            )
    finally:
        writer.stop()
    if quiet_seconds <= 20:
        assert len(writer.files_written) == 1
        actual, rate = soundfile.read(writer.files_written[0], dtype='float32')
        assert rate == 48_000
        np.testing.assert_array_equal(actual, np.concatenate(samples))
        assert [
            (s.start, s.count) for s in writer.file_spans[writer.files_written[0]]
        ] == [(0, len(actual))]
    else:
        assert len(writer.files_written) == 2
        first, rate = soundfile.read(writer.files_written[0], dtype='float32')
        second, _ = soundfile.read(writer.files_written[1], dtype='float32')
        assert rate == 48_000
        np.testing.assert_array_equal(first, np.concatenate(samples[:11]))
        np.testing.assert_array_equal(second, np.concatenate(samples[-11:]))
        assert writer.file_start_frames[writer.files_written[1]] == 12 * 48_000


def test_tiny_blocks_and_timestamp_jumps_preserve_audio_and_capture_gaps(
    tmp_path: Path,
) -> None:
    writer = make_writer(tmp_path, TimeSettings[int](shortest_file_time=48_000))
    sizes = [24_000, 1, 23_999, 48_000]
    samples = np.linspace(-0.5, 0.5, sum(sizes), dtype=np.float32)
    cursor = 0
    try:
        for i, size in enumerate(sizes):
            writer.receive_update(
                Block(block=samples[cursor : cursor + size]),
                [1.0, 1.001, 0.5, 10.0][i],
                should_record=True,
                timeline_frame=cursor + size + (480 if i == 3 else 0),
            )
            cursor += size
    finally:
        writer.stop()
    assert len(writer.files_written) == 1
    path = writer.files_written[0]
    actual, rate = soundfile.read(path, dtype='float32')
    assert rate == 48_000
    np.testing.assert_array_equal(actual, samples)
    assert [(s.asset_start, s.start, s.count) for s in writer.file_spans[path]] == [
        (0, 0, 48_000),
        (48_000, 48_480, 48_000),
    ]


@pytest.mark.parametrize('publish_before_discard', [False, True])
def test_discard_and_reopen_report_distinct_file_lifecycles(
    tmp_path: Path, publish_before_discard: bool
) -> None:
    writer = make_writer(tmp_path, TimeSettings[int](shortest_file_time=96_000))
    events = SourceFileEvents([writer])
    loud = Block(block=np.full(48_000, 0.25, dtype=np.float32))
    quiet = Block(block=np.zeros(48_000, dtype=np.float32))
    writer.receive_update(loud, 1.0, should_record=True, timeline_frame=48_000)
    first = writer.active_files[0]
    if publish_before_discard:
        assert events.new_files([writer], 32)[0] == [first]
    writer.receive_update(quiet, 2.0, should_record=False, timeline_frame=96_000)
    assert not first.exists()
    # Reuse the wall-clock second deliberately, as a clock jump can do.
    writer.receive_update(loud, 1.0, should_record=True, timeline_frame=144_000)
    second = writer.active_files[0]
    writer.receive_update(loud, 2.0, should_record=True, timeline_frame=192_000)
    writer.stop()
    paths, records = events.new_files([writer], 32)
    assert paths == ([second] if publish_before_discard else [first, second])
    assert [r.start_frame for r in records] == (
        [96_000] if publish_before_discard else [0, 96_000]
    )
    assert first != second
    assert events.discarded([writer]) == [first]
    assert events.finished([writer]) == [second]
    assert events.new_files([writer], 32) == ([], [])
    actual, rate = soundfile.read(second, dtype='float32')
    assert rate == 48_000
    np.testing.assert_array_equal(actual, np.full(96_000, 0.25, dtype=np.float32))
