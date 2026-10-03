import signal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile
import tdir
from pydantic import BaseModel, ConfigDict
from ufor.encoding import Format, Subtype

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.audio.file_opener import FileOpener
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.base.types import SDTYPE, SdType
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.file_source import FileSource
from recs.cfg.time_settings import TimeSettings
from recs.cfg.track import Track
from test import conftest

SAMPLERATE = 44_100
TIMES = {'quiet_before_start': 30, 'quiet_after_end': 40, 'stop_after_quiet': 50}

II = [np.array((1, -1, 1, -1), dtype=SDTYPE)]
OO = [np.array((0, 0, 0, 0), dtype=SDTYPE)]


class Case(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    arrays: list[np.ndarray]
    result: list[list[int]]
    format: Format = Format.wav
    longest_file_time: int = 0
    name: str = ''
    sdtype: SdType | None = None
    shortest_file_time: int = 1


BASE = Case(
    name='base',
    arrays=(17 * OO) + (4 * II) + (40 * OO) + II + (51 * OO) + (19 * II),
    result=[[28, 16, 40], [28, 4, 40], [28, 76]],
)
LONGEST_FILE_TIME = Case(
    name='longest_file_time',
    arrays=100 * II,
    longest_file_time=210,
    result=[[0, 208], [0, 192]],
)


TEST_CASES = (
    BASE,
    BASE.model_copy(update={'sdtype': SdType.int16}),
    BASE.model_copy(update={'sdtype': SdType.int32}),
    BASE.model_copy(update={'sdtype': SdType.float32}),
    Case(
        name='not sure',
        arrays=(4 * II) + (3 * OO) + II + (2000 * OO) + (3 * II),
        result=[[0, 16, 12, 4, 40], [28, 12]],
    ),
    LONGEST_FILE_TIME,
    LONGEST_FILE_TIME.model_copy(update={'format': Format.flac}),
    LONGEST_FILE_TIME.model_copy(update={'format': Format.wav}),
    LONGEST_FILE_TIME.model_copy(update={'format': Format.mp3}),
)


@pytest.mark.parametrize('case', TEST_CASES)
@tdir
def test_channel_writer(case, mock_devices):
    cfg = Cfg(formats=[case.format], sdtype=case.sdtype)
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        longest_file_time=case.longest_file_time,
        shortest_file_time=case.shortest_file_time,
        **TIMES,
    )

    timestamp = conftest.TIMESTAMP
    with ChannelWriter(cfg, times=times, track=track) as writer:
        for a in case.arrays:
            b = Block(block=a)
            writer._receive_block(b, timestamp, writer.should_record(b))
            timestamp += len(b) / SAMPLERATE

    files = sorted(writer.files_written)
    suffix = '.' + case.format
    assert all(f.suffix == suffix for f in files)

    contents, samplerates = zip(*(soundfile.read(f) for f in files), strict=False)

    assert all(s == SAMPLERATE for s in samplerates)
    result = [list(_on_and_off_segments(c)) for c in contents]
    assert case.result == result

    with soundfile.SoundFile(files[0]) as fp:
        if case.format == Format.flac and case.sdtype is None:
            assert fp.subtype.lower() == Subtype.pcm_24

        if case.sdtype in (None, SdType.float32) and soundfile.check_format(
            case.format, Subtype.float
        ):
            assert fp.subtype.lower() == Subtype.float

        if case.format == Format.mp3:
            assert fp.date == '2023'
            assert fp.software == ''
        else:
            assert fp.date.startswith('2023-10-15T16:49:21')
            assert fp.software.startswith('https://github.com/rec/recs')


def test_failed_second_format_closes_and_removes_first_output(
    tmp_path: Path, mock_devices: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = Cfg(formats=[Format.wav, Format.flac])
    track = cfg.aliases.to_track('Ext+2')
    writer = ChannelWriter(
        cfg, cfg.times.scale(track.source.samplerate), track, tmp_path
    )
    original_create = FileOpener.create
    opened: list[soundfile.SoundFile] = []

    def create(
        self: FileOpener, metadata: dict[str, str], path: Path
    ) -> soundfile.SoundFile:
        if self.format == Format.flac:
            raise OSError('disk full')
        result = original_create(self, metadata, path)
        opened.append(result)
        return result

    monkeypatch.setattr(FileOpener, 'create', create)

    with pytest.raises(OSError, match='disk full'):
        writer._open(0, conftest.TIMESTAMP)

    assert opened[0].closed
    assert not list(tmp_path.rglob('*.wav'))
    assert not writer.files_written


def test_channel_noise_floor_overrides_global_floor(mock_devices: None) -> None:
    cfg = Cfg(noise_floor=30, channel_noise_floors={'Ext': {'1-2': 20}})
    track = cfg.aliases.to_track('Ext+1-2')
    block = Block(block=np.tile(np.array([[-0.05, -0.05], [0.05, 0.05]]), (50, 1)))

    writer = ChannelWriter(cfg, cfg.times.scale(track.source.samplerate), track)

    assert not writer.should_record(block)
    writer.set_cfg(
        Cfg(noise_floor=30, channel_noise_floors={'Ext': {'1-2': None}}),
        cfg.times.scale(track.source.samplerate),
    )
    assert writer.should_record(block)


@tdir
def test_channel_writer_record_everything_ignores_longest_file_time(
    mock_devices: None,
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        longest_file_time=4,
        quiet_before_start=0,
        quiet_after_end=0,
        record_everything=True,
        shortest_file_time=1,
        stop_after_quiet=50,
    )
    block = Block(block=II[0])
    timestamp = conftest.TIMESTAMP
    expected_dt = len(block) / track.source.samplerate

    with ChannelWriter(cfg, times=times, track=track) as writer:
        writer.receive_update(block, timestamp)
        writer.receive_update(block, timestamp + expected_dt)
        writer.receive_update(block, timestamp + expected_dt * 2)

    assert len(writer.files_written) == 1
    with soundfile.SoundFile(writer.files_written[0]) as fp:
        assert fp.frames == 3 * len(block)


@tdir
def test_channel_writer_closes_on_forward_timestamp_gap(
    mock_devices: None,
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        shortest_file_time=1,
        stop_after_quiet=50,
    )
    block = Block(block=II[0])

    with ChannelWriter(cfg, times=times, track=track) as writer:
        writer.receive_update(block, conftest.TIMESTAMP)
        writer.receive_update(block, conftest.TIMESTAMP + 1)

    assert len(writer.files_written) == 2


@tdir
def test_channel_writer_record_everything_ignores_forward_timestamp_gap(
    mock_devices: None,
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        record_everything=True,
        shortest_file_time=1,
        stop_after_quiet=50,
    )
    block = Block(block=II[0])

    with ChannelWriter(cfg, times=times, track=track) as writer:
        writer.receive_update(block, conftest.TIMESTAMP)
        writer.receive_update(block, conftest.TIMESTAMP + 1)

    assert len(writer.files_written) == 1
    with soundfile.SoundFile(writer.files_written[0]) as fp:
        assert fp.frames == 2 * len(block)


@tdir
def test_channel_writer_keeps_backward_timestamp_jump_in_same_file(
    mock_devices: None,
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        shortest_file_time=1,
        stop_after_quiet=50,
    )
    block = Block(block=II[0])

    with ChannelWriter(cfg, times=times, track=track) as writer:
        writer.receive_update(block, conftest.TIMESTAMP)
        writer.receive_update(block, conftest.TIMESTAMP - 1)

    assert len(writer.files_written) == 1
    with soundfile.SoundFile(writer.files_written[0]) as fp:
        assert fp.frames == 2 * len(block)


@tdir
def test_channel_writer_record_everything_keeps_short_file(
    mock_devices: None,
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        record_everything=True,
        shortest_file_time=100,
        stop_after_quiet=50,
    )
    block = Block(block=II[0])

    with ChannelWriter(cfg, times=times, track=track) as writer:
        writer.receive_update(block, conftest.TIMESTAMP)

    assert len(writer.files_written) == 1
    assert writer.files_written[0].exists()
    with soundfile.SoundFile(writer.files_written[0]) as fp:
        assert fp.frames == len(block)


@tdir
def test_channel_writer_removes_discarded_short_file_from_state(
    mock_devices: None,
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        shortest_file_time=100,
        stop_after_quiet=0,
    )
    block = Block(block=II[0])

    with ChannelWriter(cfg, times=times, track=track) as writer:
        writer.receive_update(block, conftest.TIMESTAMP, should_record=True)
        files = list(writer.files_written)
        state = writer.receive_update(block, conftest.TIMESTAMP, should_record=False)

    assert len(files) == 1
    assert not files[0].exists()
    assert writer.files_written == []
    assert state.file_count == -1


def test_channel_writer_uses_precomputed_recording_decision(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    block = Block(block=II[0])
    writer = ChannelWriter(cfg, TimeSettings[int](stop_after_quiet=50), track)
    monkeypatch.setattr(
        writer,
        'should_record',
        lambda block: pytest.fail('should_record should not be recomputed'),
    )

    writer.receive_update(block, conftest.TIMESTAMP, should_record=False)

    assert not writer._state().is_active


@tdir
def test_channel_writer_records_max_write_seconds(
    monkeypatch: pytest.MonkeyPatch, mock_devices: None
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        shortest_file_time=1,
        stop_after_quiet=50,
    )
    values = iter([0.0, 0.25, 0.25, 0.25, 0.25])
    monkeypatch.setattr(
        'recs.audio.channel_writer.time.monotonic', lambda: next(values)
    )
    writer = ChannelWriter(cfg, times=times, track=track)

    writer._receive_block(Block(block=II[0]), conftest.TIMESTAMP, True)

    assert writer._state().max_write_seconds == 0.25


def test_channel_writer_flushes_after_interval_even_during_quiet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )
    cfg = Cfg(output_directory=str(tmp_path), formats=[Format.wav])
    writer = ChannelWriter(
        cfg,
        TimeSettings[int](quiet_after_end=48_000, stop_after_quiet=96_000),
        Track(source, '1'),
    )
    clock = [0.0]
    monkeypatch.setattr(
        'recs.audio.channel_writer.time', SimpleNamespace(monotonic=lambda: clock[0])
    )
    original_flush = soundfile.SoundFile.flush
    flushed: list[Path] = []

    def flush(file: soundfile.SoundFile) -> None:
        if Path(file.name) in writer.files_written:
            flushed.append(Path(file.name))
        original_flush(file)

    monkeypatch.setattr(soundfile.SoundFile, 'flush', flush)
    audio = Block(block=np.ones((24_000, 1), dtype=np.int16))
    quiet = Block(block=np.zeros((48_000, 1), dtype=np.int16))

    writer.receive_update(audio, 0.5, should_record=True, timeline_frame=24_000)
    assert not flushed
    assert np.shares_memory(writer._recovery_blocks[0].block, audio.block)

    clock[0] = 1.0
    writer.receive_update(quiet, 1.5, should_record=False, timeline_frame=72_000)
    assert flushed == list(writer.files_written)

    clock[0] = 1.5
    writer.receive_update(audio, 2.0, should_record=True, timeline_frame=96_000)
    assert flushed == list(writer.files_written) * 2
    writer.stop()


def test_channel_writer_flushes_fast_queued_audio_by_frame_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )
    writer = ChannelWriter(
        Cfg(output_directory=str(tmp_path), formats=[Format.wav]),
        TimeSettings[int](),
        Track(source, '1'),
    )
    monkeypatch.setattr(
        'recs.audio.channel_writer.time', SimpleNamespace(monotonic=lambda: 0.0)
    )
    original_flush = soundfile.SoundFile.flush
    flushed = 0

    def flush(file: soundfile.SoundFile) -> None:
        nonlocal flushed
        if Path(file.name) in writer.files_written:
            flushed += 1
        original_flush(file)

    monkeypatch.setattr(soundfile.SoundFile, 'flush', flush)
    audio = Block(block=np.ones((24_000, 1), dtype=np.int16))
    writer.receive_update(audio, 0.5, should_record=True, timeline_frame=24_000)
    assert flushed == 0
    writer.receive_update(audio, 1.0, should_record=True, timeline_frame=48_000)
    assert flushed == 1
    writer.stop()


def test_file_input_recovery_does_not_retain_large_read_buffer_or_sync_fast_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_file = tmp_path / 'input.wav'
    soundfile.write(input_file, np.ones(48_000, dtype=np.int16), 48_000)
    source = FileSource(input_file)
    writer = ChannelWriter(
        Cfg(output_directory=str(tmp_path / 'output'), formats=[Format.wav]),
        TimeSettings[int](),
        Track(source, '1'),
    )
    monkeypatch.setattr(
        'recs.audio.channel_writer.time', SimpleNamespace(monotonic=lambda: 0.0)
    )
    original_flush = soundfile.SoundFile.flush
    flushed = 0

    def flush(file: soundfile.SoundFile) -> None:
        nonlocal flushed
        if Path(file.name) in writer.files_written:
            flushed += 1
        original_flush(file)

    monkeypatch.setattr(soundfile.SoundFile, 'flush', flush)
    large_read = np.ones((48_000 * 4, 1), dtype=np.int16)
    writer.receive_update(
        Block(block=large_read[:48_000]),
        1.0,
        should_record=True,
        timeline_frame=48_000,
    )

    assert not np.shares_memory(writer._recovery_blocks[0].block, large_read)
    assert flushed == 0
    writer.stop()


def test_flush_error_preserves_replay_audio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )
    cfg = Cfg(output_directory=str(tmp_path), formats=[Format.wav])
    times = TimeSettings[int](stop_after_quiet=96_000)
    track = Track(source, '1')
    writer = ChannelWriter(cfg, times, track, tmp_path / 'old')
    clock = [0.0]
    monkeypatch.setattr(
        'recs.audio.channel_writer.time', SimpleNamespace(monotonic=lambda: clock[0])
    )
    audio = Block(block=np.ones((24_000, 1), dtype=np.int16))
    writer.receive_update(audio, 0.5, should_record=True, timeline_frame=24_000)
    original_flush = soundfile.SoundFile.flush
    failed_once = False

    def fail_once(file: soundfile.SoundFile) -> None:
        nonlocal failed_once
        if not failed_once and Path(file.name) in writer.files_written:
            failed_once = True
            raise OSError('card disconnected during sync')
        original_flush(file)

    monkeypatch.setattr(soundfile.SoundFile, 'flush', fail_once)
    clock[0] = 1.0
    with pytest.raises(OSError, match='card disconnected during sync'):
        writer.receive_update(audio, 1.0, should_record=True, timeline_frame=48_000)
    writer.stop_after_write_error()

    replacement = ChannelWriter(cfg, times, track, tmp_path / 'new')
    writer.replay_to(replacement)
    replacement.stop()
    assert soundfile.info(replacement.files_written[0]).frames == 48_000


def test_recovery_replays_last_attempted_frames_at_original_position(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )
    cfg = Cfg(
        output_directory=str(tmp_path),
        formats=[Format.wav],
        sdtype=SdType.int16,
        shortest_file_time=2.0,
        flush_time=0,
        flush_overlap_time=0.5,
    )
    times = cfg.times.scale(48_000)
    track = Track(source, '1')
    old = ChannelWriter(cfg, times, track, tmp_path / 'old')
    first = Block(block=np.full((48_000, 1), 100, dtype=np.int16))
    failed = Block(block=np.full((48_000, 1), 200, dtype=np.int16))
    later = Block(block=np.full((48_000, 1), 300, dtype=np.int16))
    old.receive_update(first, 1.0, should_record=True, timeline_frame=48_000)
    original_write = soundfile.SoundFile.write
    failed_once = False

    def fail_next_write(file: soundfile.SoundFile, data: np.ndarray) -> None:
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise OSError('card disconnected')
        original_write(file, data)

    monkeypatch.setattr(soundfile.SoundFile, 'write', fail_next_write)
    with pytest.raises(OSError, match='card disconnected'):
        old.receive_update(failed, 2.0, should_record=True, timeline_frame=96_000)
    old.stop_after_write_error()

    replacement = ChannelWriter(cfg, times, track, tmp_path / 'new')
    old.replay_to(replacement)
    replacement.receive_update(later, 3.0, should_record=True, timeline_frame=144_000)
    replacement.stop()

    path = replacement.files_written[0]
    samples, rate = soundfile.read(path, dtype='int16')
    assert rate == 48_000
    assert len(samples) == 72_000
    assert np.all(samples[:24_000] == 200)
    assert np.all(samples[24_000:] == 300)
    assert replacement.file_start_frames[path] == 72_000
    assert replacement.file_spans[path][0].start == 72_000


@tdir
def test_channel_writer_trims_stored_quiet_without_delaying_close(
    mock_devices: None,
) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=4,
        shortest_file_time=1,
        stop_after_quiet=10,
    )
    block = Block(block=II[0])
    writer = ChannelWriter(cfg, times=times, track=track)

    writer.receive_update(block, conftest.TIMESTAMP, should_record=True)
    assert writer._state().is_active

    writer.receive_update(block, conftest.TIMESTAMP, should_record=False)
    writer.receive_update(block, conftest.TIMESTAMP, should_record=False)
    assert writer._blocks.duration == 4
    assert writer.quiet_frames == 8
    assert writer._state().is_active

    writer.receive_update(block, conftest.TIMESTAMP, should_record=False)

    assert writer._blocks.duration == 0
    assert writer.quiet_frames == 12
    assert not writer._state().is_active


@tdir
def test_channel_writer_closes_active_file_on_signal(mock_devices: None) -> None:
    cfg = Cfg(formats=[Format.wav])
    track = cfg.aliases.to_track('Ext+2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        shortest_file_time=1,
        stop_after_quiet=50,
    )
    block = Block(block=II[0])
    files: list[Path] = []

    with pytest.raises(KeyboardInterrupt):
        with (
            raise_keyboard_interrupt_on_signal(),
            ChannelWriter(cfg, times=times, track=track) as writer,
        ):
            writer._receive_block(block, conftest.TIMESTAMP, True)
            files = list(writer.files_written)
            signal.raise_signal(signal.SIGTERM)

    assert len(files) == 1
    with soundfile.SoundFile(files[0]) as fp:
        assert fp.frames == len(block)


@tdir
def test_channel_writer_uses_track_name_for_new_files(mock_devices: None) -> None:
    cfg = Cfg(formats=[Format.wav], output_directory='takes')
    track = cfg.aliases.to_track('Ext + 1-2')
    times = TimeSettings[int](
        quiet_before_start=0,
        quiet_after_end=0,
        shortest_file_time=1,
        stop_after_quiet=50,
    )
    block = Block(block=np.array(((1, -1), (1, -1)), dtype=SDTYPE))

    with ChannelWriter(cfg, times=times, track=track) as writer:
        writer.set_track_names({'Ext': {'Stereo Pair': 2}})
        writer._receive_block(block, conftest.TIMESTAMP, True)

    files = list(writer.files_written)
    assert len(files) == 1
    assert files[0].match('takes/audio/Stereo Pair + 20231015-164921.wav')


def _on_and_off_segments(it):
    pb = False
    pi = 0

    if it := list(it):
        for i, x in enumerate(it):
            if (b := bool(x)) != pb:
                yield i - pi
                pb = b
                pi = i
        yield i + 1 - pi
