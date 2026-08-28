from pathlib import Path

import numpy as np
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture

from recs.audio.block import Block
from recs.audio.live_waveform import LiveWaveform
from recs.base.waveform import WaveformTrackLayout

SAMPLE_RATE = 48_000
BUCKET_FRAMES = 960
BUCKET_MILLISECONDS = 20
BATCH_MILLISECONDS = 100


def test_live_waveform_reduces_mono_wav(
    tmp_path: Path, data_regression: DataRegressionFixture
) -> None:
    audio = _write_wav(tmp_path / 'mono.wav', channels=1)
    waveform = LiveWaveform(
        source='Mic',
        sample_rate=SAMPLE_RATE,
        tracks=[WaveformTrackLayout(channels=[1], name='Vocal')],
        generation=1,
        bucket_milliseconds=BUCKET_MILLISECONDS,
        batch_milliseconds=BATCH_MILLISECONDS,
    )

    batches = waveform.receive([Block(block=audio)], 0, 100.0)

    assert len(batches) == 10
    data_regression.check(
        {
            'first': batches[0].model_dump(),
            'last': batches[-1].model_dump(),
        }
    )


def test_live_waveform_preserves_stereo_track_grouping(tmp_path: Path) -> None:
    audio = _write_wav(tmp_path / 'stereo.wav', channels=2)
    waveform = LiveWaveform(
        source='Mixer',
        sample_rate=SAMPLE_RATE,
        tracks=[WaveformTrackLayout(channels=[2, 3], name='Keys')],
        generation=1,
        bucket_milliseconds=BUCKET_MILLISECONDS,
        batch_milliseconds=BATCH_MILLISECONDS,
    )

    batches = waveform.receive([Block(block=audio)], 0, 100.0)

    assert waveform.layout.tracks == [WaveformTrackLayout(channels=[2, 3], name='Keys')]
    assert len(batches[0].tracks) == 1
    assert batches[0].tracks[0].channels == [2, 3]
    assert len(batches[0].tracks[0].minimum) == 2


def test_live_waveform_uses_configured_timing(tmp_path: Path) -> None:
    audio = _write_wav(tmp_path / 'configured.wav', channels=1)
    waveform = LiveWaveform(
        source='Mic',
        sample_rate=SAMPLE_RATE,
        tracks=[WaveformTrackLayout(channels=[1])],
        generation=1,
        bucket_milliseconds=10,
        batch_milliseconds=40,
    )

    batches = waveform.receive([Block(block=audio)], 0, 100.0)

    assert waveform.layout.bucket_frames == 480
    assert len(batches) == 25
    assert all(len(b.present) == 4 for b in batches)


def test_live_waveform_marks_partial_bucket_across_frame_gap(
    tmp_path: Path,
) -> None:
    audio = _write_wav(tmp_path / 'gap.wav', channels=1)
    waveform = LiveWaveform(
        source='Mic',
        sample_rate=SAMPLE_RATE,
        tracks=[WaveformTrackLayout(channels=[1])],
        generation=1,
        bucket_milliseconds=BUCKET_MILLISECONDS,
        batch_milliseconds=BATCH_MILLISECONDS,
    )

    assert waveform.receive([Block(block=audio[:480])], 0, 100.0) == []
    batches = waveform.receive([Block(block=audio[1_200:7_680])], 1_200, 100.025)

    assert batches[0].start_frame == 0
    assert batches[0].present == [False]
    assert batches[1].start_frame == 1_920
    assert batches[1].present == [True] * 5


def _write_wav(path: Path, channels: int) -> np.ndarray:
    peaks = np.repeat(np.arange(1, 51, dtype=np.float32) / 100, BUCKET_FRAMES)
    phase = np.tile(np.linspace(-1, 1, BUCKET_FRAMES, dtype=np.float32), 50)
    mono = peaks * phase
    audio = mono[:, np.newaxis]
    if channels == 2:
        audio = np.column_stack((mono, mono * 0.5))
    soundfile.write(path, audio, SAMPLE_RATE, subtype='FLOAT')
    result, sample_rate = soundfile.read(path, dtype='float32', always_2d=True)
    assert sample_rate == SAMPLE_RATE
    return result
