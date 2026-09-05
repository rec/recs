from pathlib import Path

import numpy as np
import pytest
import soundfile

from recs.base.errors import RecsError
from recs.edit import autocalibrate
from recs.edit.cli import main
from recs.edit.composition import execute_composition, parse_composition
from recs.edit.record import AudioFragment, ResolvedSource
from recs.ui import session_record

SAMPLE_RATE = 48_000
WINDOW_FRAMES = 4_800


def test_calibration_uses_each_tracks_first_sustained_silence(
    tmp_path: Path,
) -> None:
    quiet = _session_audio(0.001)
    noisy = _session_audio(0.02)
    quiet_source = _source(tmp_path, 'quiet.wav', quiet)
    noisy_source = _source(tmp_path, 'noisy.wav', noisy)
    settings = autocalibrate.CalibrationSettings()

    quiet_result = autocalibrate.calibrate_threshold(
        'device:quiet',
        lambda: autocalibrate.level_windows(quiet_source, settings),
        settings,
    )
    noisy_result = autocalibrate.calibrate_threshold(
        'device:noisy',
        lambda: autocalibrate.level_windows(noisy_source, settings),
        settings,
    )

    assert quiet_result.silence_start == SAMPLE_RATE // 2
    assert quiet_result.silence_end == SAMPLE_RATE * 3 // 2
    assert quiet_result.measured_noise_floor == pytest.approx(60.0, abs=0.2)
    assert quiet_result.noise_floor == pytest.approx(54.0, abs=0.2)
    assert noisy_result.measured_noise_floor == pytest.approx(34.0, abs=0.2)
    assert noisy_result.noise_floor == pytest.approx(28.0, abs=0.2)


def test_detection_uses_fixed_calibration_when_noise_later_changes(
    tmp_path: Path,
) -> None:
    audio = _session_audio(0.001)
    audio[SAMPLE_RATE * 5 // 2 :] += _tone(len(audio) - SAMPLE_RATE * 5 // 2, 0.02)
    source = _source(tmp_path, 'changed-noise.wav', audio)
    calibration = autocalibrate.CalibrationSettings()
    threshold = autocalibrate.calibrate_threshold(
        'device:voice',
        lambda: autocalibrate.level_windows(source, calibration),
        calibration,
    )
    silence = autocalibrate.SilenceSettings(
        quiet_before_frames=0,
        quiet_after_frames=0,
        stop_after_quiet_frames=0,
        shortest_file_frames=1,
    )

    intervals = autocalibrate.detect_intervals(
        autocalibrate.level_windows(source, calibration), threshold, silence
    )

    assert intervals == [
        autocalibrate.FrameRange(start=0, end=SAMPLE_RATE // 2),
        autocalibrate.FrameRange(start=SAMPLE_RATE * 3 // 2, end=SAMPLE_RATE * 4),
    ]


def test_silence_detection_pads_splits_and_respects_source_gaps() -> None:
    threshold = autocalibrate.CalibratedThreshold(
        source='device:voice',
        silence_start=0,
        silence_end=WINDOW_FRAMES * 2,
        provisional_quiet_level_dbfs=-60,
        measured_noise_floor=60,
        noise_floor=54,
        observed_window_count=7,
        window_count=2,
    )
    windows = [
        _window(0, -20, 0, WINDOW_FRAMES * 6),
        _window(1, -80, 0, WINDOW_FRAMES * 6),
        _window(2, -20, 0, WINDOW_FRAMES * 6),
        _window(3, -80, 0, WINDOW_FRAMES * 6),
        _window(5, -20, WINDOW_FRAMES * 5, WINDOW_FRAMES * 7),
        _window(6, -20, WINDOW_FRAMES * 5, WINDOW_FRAMES * 7),
    ]
    settings = autocalibrate.SilenceSettings(
        quiet_before_frames=WINDOW_FRAMES,
        quiet_after_frames=WINDOW_FRAMES,
        stop_after_quiet_frames=WINDOW_FRAMES,
        shortest_file_frames=1,
        longest_file_frames=WINDOW_FRAMES * 2,
    )

    assert autocalibrate.detect_intervals(windows, threshold, settings) == [
        autocalibrate.FrameRange(start=0, end=WINDOW_FRAMES * 2),
        autocalibrate.FrameRange(start=WINDOW_FRAMES * 2, end=WINDOW_FRAMES * 4),
        autocalibrate.FrameRange(start=WINDOW_FRAMES * 5, end=WINDOW_FRAMES * 7),
    ]


def test_calibration_rejects_tracks_without_sustained_quiet() -> None:
    settings = autocalibrate.CalibrationSettings(
        window_frames=WINDOW_FRAMES,
        minimum_silence_frames=WINDOW_FRAMES * 2,
        candidate_tolerance_db=0,
    )
    windows = [
        _window(i, -80 if i % 2 else -20, 0, WINDOW_FRAMES * 8) for i in range(8)
    ]

    with pytest.raises(RecsError, match='no sustained silence'):
        autocalibrate.calibrate_threshold(
            'device:voice', lambda: iter(windows), settings
        )


def test_autocalibrate_toml_round_trips() -> None:
    value = autocalibrate.AutocalibrateEdit(
        record=Path('../session-record.jsonl'),
        channels=['device:voice'],
        sample_rate=SAMPLE_RATE,
        thresholds=[
            autocalibrate.CalibratedThreshold(
                source='device:voice',
                silence_start=WINDOW_FRAMES,
                silence_end=WINDOW_FRAMES * 2,
                provisional_quiet_level_dbfs=-60,
                measured_noise_floor=60,
                noise_floor=54,
                observed_window_count=8,
                window_count=1,
            )
        ],
    )

    assert (
        autocalibrate.parse_autocalibrate(autocalibrate.canonical_autocalibrate(value))
        == value
    )


def test_autocalibrate_writes_segmented_session(tmp_path: Path) -> None:
    audio = _session_audio(0.001)
    record_path, audio_path = _record(tmp_path, audio)
    original = audio_path.read_bytes()
    edit = autocalibrate.AutocalibrateEdit(
        record=Path('session-record.jsonl'),
        channels=['device:voice'],
        silence=autocalibrate.SilenceSettings(
            quiet_before_frames=0,
            quiet_after_frames=0,
            stop_after_quiet_frames=0,
            shortest_file_frames=1,
        ),
        output=autocalibrate.AutocalibrateOutput(
            format='wav',
            subtype='float',
        ),
    )
    destination = tmp_path / 'edited'

    result_path = autocalibrate.execute_autocalibrate(
        edit, record_path.parent, destination
    )

    first, rate = soundfile.read(
        destination / 'audio/device-voice/0001.wav',
        dtype='float32',
        always_2d=True,
    )
    second, second_rate = soundfile.read(
        destination / 'audio/device-voice/0002.wav',
        dtype='float32',
        always_2d=True,
    )
    np.testing.assert_array_equal(first[:, 0], audio[: SAMPLE_RATE // 2])
    np.testing.assert_array_equal(
        second[:, 0], audio[SAMPLE_RATE * 3 // 2 : SAMPLE_RATE * 5 // 2]
    )
    assert rate == second_rate == SAMPLE_RATE
    assert audio_path.read_bytes() == original

    result = session_record.read(result_path)
    finished = [f for f in result.files if f.type == 'file_finished']
    assert [(f.frame_count, f.quantity_count) for f in finished] == [
        (SAMPLE_RATE // 2, SAMPLE_RATE // 2),
        (SAMPLE_RATE * 5 // 2, SAMPLE_RATE),
    ]
    assert {f.track_name for f in finished} == {'device-voice'}
    canonical = autocalibrate.parse_autocalibrate(
        (destination / 'edit.toml').read_text()
    )
    assert canonical.sample_rate == SAMPLE_RATE
    assert canonical.thresholds[0].source == 'device:voice'
    assert 'First silence: 24000:72000' in autocalibrate.autocalibrate_summary(
        autocalibrate.prepare_autocalibrate(canonical, destination, tmp_path / 'again')
    )


def test_options_convert_durations_to_source_frames(tmp_path: Path) -> None:
    record_path, _ = _record(tmp_path, _session_audio(0.001))
    options = autocalibrate.AutocalibrateOptions(
        channel=['device:voice'],
        window_time=0.05,
        minimum_silence_time=0.25,
        quiet_before=0.5,
        quiet_after=0.75,
        stop_after_quiet=3,
        shortest_file_time=0.2,
        longest_file_time=10,
        format='wav',
        subtype='float',
    )

    value = autocalibrate.autocalibrate_from_options(record_path, options)

    assert value.calibration.window_frames == 2_400
    assert value.calibration.minimum_silence_frames == 12_000
    assert value.silence == autocalibrate.SilenceSettings(
        quiet_before_frames=24_000,
        quiet_after_frames=36_000,
        stop_after_quiet_frames=144_000,
        shortest_file_frames=9_600,
        longest_file_frames=480_000,
    )


def test_cli_dry_run_discovers_silence_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record_path, _ = _record(tmp_path, _session_audio(0.001))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.chdir(tmp_path)

    assert main(['autocalibrate', str(record_path), '--dry-run']) == 0

    output = capsys.readouterr().out
    assert 'device:voice:' in output
    assert 'Calibration: first sustained silence per track; fixed thereafter' in output
    assert 'Provisional quiet: -60.0 dBFS' in output
    assert 'First silence: 24000:72000' in output
    assert 'Observed windows: 40' in output
    assert 'Measured noise: -60.0 dBFS' in output
    assert 'Output: 1 file, 192000 frames (4.000 seconds)' in output
    assert list(tmp_path.glob('* edit')) == []


def test_composition_executes_autocalibration_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record_path, _ = _record(tmp_path, _session_audio(0.001))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    composition_path = tmp_path / 'composition.toml'
    composition_path.write_text(
        'schema_version = 1\n'
        'kind = "composition"\n'
        '[[edits]]\n'
        'command = "autocalibrate"\n'
        'channel = ["device:voice"]\n'
        'format = "wav"\n'
        'subtype = "float"\n'
    )
    destination = tmp_path / 'composed'

    result_path = execute_composition(
        parse_composition(composition_path.read_text()),
        composition_path,
        record_path,
        destination,
    )

    assert result_path == destination / '001-autocalibrate/session-record.jsonl'
    result = session_record.read(result_path)
    assert [f.track_name for f in result.files if f.type == 'file_finished'] == [
        'device-voice'
    ]
    assert (destination / 'commands/001-autocalibrate.toml').is_file()


def _session_audio(noise_amplitude: float) -> np.ndarray:
    audio = _tone(SAMPLE_RATE * 4, noise_amplitude)
    audio[: SAMPLE_RATE // 2] += _tone(SAMPLE_RATE // 2, 0.4)
    audio[SAMPLE_RATE * 3 // 2 : SAMPLE_RATE * 5 // 2] += _tone(SAMPLE_RATE, 0.4)
    return audio


def _record(directory: Path, audio: np.ndarray) -> tuple[Path, Path]:
    source_directory = directory / 'source'
    source_directory.mkdir()
    audio_path = source_directory / 'voice.wav'
    soundfile.write(audio_path, audio, SAMPLE_RATE, subtype='FLOAT')
    record_path = source_directory / 'session-record.jsonl'
    writer = session_record.SessionRecordWriter(
        record_path, started_at='start', session_id='input'
    )
    values = {
        'media_type': 'audio',
        'stream_id': 'audio:device:voice',
        'format': 'wav',
        'path': 'voice.wav',
        'source': 'device',
        'track_name': 'voice',
        'source_channels': [1],
        'channels': 1,
        'sample_rate': SAMPLE_RATE,
        'bit_depth': 32,
    }
    writer.write(
        session_record.FileRecord(
            type='file_started', timestamp='start', frame_count=0, **values
        )
    )
    writer.write(
        session_record.FileRecord(
            type='file_finished',
            timestamp='end',
            frame_count=len(audio),
            quantity_count=len(audio),
            **values,
        )
    )
    writer.write(
        session_record.SessionFooter(
            ended_at='end', duration_seconds=len(audio) / SAMPLE_RATE
        )
    )
    writer.close()
    return record_path, audio_path


def _tone(frames: int, amplitude: float) -> np.ndarray:
    positions = np.arange(frames, dtype=np.float64)
    return (amplitude * np.sin(2 * np.pi * 1_000 * positions / SAMPLE_RATE)).astype(
        np.float32
    )


def _source(directory: Path, name: str, audio: np.ndarray) -> ResolvedSource:
    path = directory / name
    soundfile.write(path, audio, SAMPLE_RATE, subtype='FLOAT')
    return ResolvedSource(
        id=name.removesuffix('.wav'),
        record=directory / 'session-record.jsonl',
        file=None,
        session_id='input',
        selector=f'device:{name}',
        channels=1,
        sample_rate=SAMPLE_RATE,
        timeline_end=len(audio),
        fragments=[
            AudioFragment(
                path=path,
                start=0,
                end=len(audio),
                channels=1,
            )
        ],
    )


def _window(
    index: int, level_dbfs: float, coverage_start: int, coverage_end: int
) -> autocalibrate.LevelWindow:
    return autocalibrate.LevelWindow(
        start=index * WINDOW_FRAMES,
        end=(index + 1) * WINDOW_FRAMES,
        level_dbfs=level_dbfs,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )
