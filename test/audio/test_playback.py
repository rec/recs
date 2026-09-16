import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile
from ufor.recording import (
    AudioFragment,
    AudioStream,
    Gap,
    GapReason,
    Recording,
    RecordingScore,
    UnmappedAudioFragment,
)
from ufor.streams import AudioType
from ufor.time import Rate, TickRange, Timebase

from recs.audio import playback
from recs.base.errors import RecsError
from recs.recording.files import sealed_asset


def test_timeline_reads_audio_at_its_recorded_position(tmp_path: Path) -> None:
    score, stream, samples = _score(tmp_path, start=48_000)

    timeline = playback.PlaybackTimeline(tmp_path, score, stream)

    data = timeline.read(0, 96_000)

    np.testing.assert_array_equal(data[:48_000], np.zeros((48_000, 2)))
    np.testing.assert_allclose(data[48_000:], samples, atol=1e-4)


@pytest.mark.parametrize('variants', [False, True])
def test_timeline_preserves_separate_spans_of_one_asset(
    tmp_path: Path, variants: bool
) -> None:
    score, stream, _ = _score(tmp_path)
    samples = np.column_stack(
        (np.linspace(-0.5, 0.5, 48_000), np.linspace(0.5, -0.5, 48_000))
    )
    soundfile.write(tmp_path / 'audio.wav', samples, 48_000, subtype='FLOAT')
    fragments = [
        AudioFragment(
            asset='audio',
            start=0,
            count=24_000,
            asset_start=24_000,
            variant_group='encoding' if variants else None,
        ),
        AudioFragment(
            asset='audio',
            start=48_000,
            count=24_000,
            asset_start=0,
            variant_group='encoding' if variants else None,
        ),
    ]
    assets = [sealed_asset(tmp_path / 'audio.wav', tmp_path, 'audio', 'wav')]
    if variants:
        soundfile.write(
            tmp_path / 'alternative.wav',
            np.zeros_like(samples),
            48_000,
            subtype='FLOAT',
        )
        assets.append(
            sealed_asset(tmp_path / 'alternative.wav', tmp_path, 'other', 'wav')
        )
        fragments += [f.model_copy(update={'asset': 'other'}) for f in fragments]
    stream = AudioStream.model_validate(
        {
            **stream.model_dump(),
            'end': 72_000,
            'fragments': fragments,
            'gaps': [
                Gap(start=24_000, end=48_000, reason=GapReason.silence_suppressed)
            ],
        }
    )
    score = score.model_copy(
        update={
            'assets': assets,
            'body': score.body.model_copy(update={'streams': [stream]}),
        }
    )
    result = playback.PlaybackTimeline(tmp_path, score, stream).read(0, 72_000)
    soundfile.write(tmp_path / 'playback.wav', result, 48_000, subtype='FLOAT')
    expected = np.concatenate(
        (samples[24_000:], np.zeros((24_000, 2)), samples[:24_000])
    ).astype(np.float32)
    np.testing.assert_array_equal(result, expected)


def test_timeline_rejects_unresolved_audio_placement(tmp_path: Path) -> None:
    score, stream, _ = _score(tmp_path)
    stream = AudioStream.model_validate(
        {
            **stream.model_dump(),
            'fragments': [],
            'unmapped_fragments': [
                UnmappedAudioFragment(
                    asset='audio',
                    count=48_000,
                    journal_range=TickRange(start=0, end=48_000),
                )
            ],
        }
    )
    with pytest.raises(RecsError, match='unresolved audio placement'):
        playback.PlaybackTimeline(tmp_path, score, stream)


def test_default_stream_uses_the_highest_stereo_pair_on_the_widest_source(
    tmp_path: Path,
) -> None:
    score, stream, _ = _score(tmp_path, channels=['input-9', 'input-10'])
    narrower = stream.model_copy(
        update={
            'name': 'narrow',
            'source_id': 'narrow-source',
            'source_name': 'Narrow',
            'track_name': '1-2',
            'stream': AudioType(timebase='audio', channels=['input-1', 'input-2']),
        }
    )
    score = score.model_copy(
        update={'body': score.body.model_copy(update={'streams': [narrower, stream]})}
    )

    assert playback.select_stream(score, None, None) == stream
    assert playback.select_stream(score, 'Narrow', '1-2') == narrower


@pytest.mark.parametrize(('value', 'expected'), [('1', (1,)), ('9-10', (9, 10))])
def test_parse_channels_accepts_a_channel_or_adjacent_pair(
    value: str, expected: tuple[int, ...]
) -> None:
    assert playback.parse_channels(value, 'channel') == expected


@pytest.mark.parametrize('value', ['0', '1-3', 'one', '1-2-3'])
def test_parse_channels_rejects_other_channel_shapes(value: str) -> None:
    with pytest.raises(RecsError):
        playback.parse_channels(value, 'channel')


def test_runner_maps_recorded_stereo_to_selected_output_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    score, stream, samples = _score(tmp_path)
    writes: list[np.ndarray] = []

    class OutputStream:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs == {
                'channels': 4,
                'dtype': 'float32',
                'samplerate': 48_000,
            }

        def start(self) -> None:
            pass

        def write(self, data: np.ndarray) -> None:
            writes.append(data)

        def close(self) -> None:
            pass

    monkeypatch.setitem(
        sys.modules, 'sounddevice', SimpleNamespace(OutputStream=OutputStream)
    )
    finished: list[None] = []
    runner = playback.PlaybackRunner(
        playback.PlaybackTimeline(tmp_path, score, stream),
        (3, 4),
        lambda: finished.append(None),
        lambda message: pytest.fail(message),
        block_frames=48_000,
    )

    runner.start()
    assert runner._thread is not None
    runner._thread.join()

    assert finished == [None]
    assert len(writes) == 1
    np.testing.assert_array_equal(writes[0][:, :2], np.zeros((48_000, 2)))
    np.testing.assert_allclose(writes[0][:, 2:], samples, atol=1e-4)


@pytest.mark.parametrize('failure_stage', ['open', 'start', 'write'])
def test_runner_reports_failure_after_output_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    score, stream, _ = _score(tmp_path)
    events: list[str] = []

    class OutputStream:
        def __init__(self, **kwargs: object) -> None:
            if failure_stage == 'open':
                raise OSError('open failed')

        def start(self) -> None:
            if failure_stage == 'start':
                raise OSError('start failed')

        def write(self, data: np.ndarray) -> None:
            raise OSError('write failed')

        def close(self) -> None:
            events.append('closed')

    monkeypatch.setitem(
        sys.modules,
        'sounddevice',
        SimpleNamespace(OutputStream=OutputStream, PortAudioError=RuntimeError),
    )
    runner = playback.PlaybackRunner(
        playback.PlaybackTimeline(tmp_path, score, stream),
        (1, 2),
        lambda: events.append('finished'),
        events.append,
    )
    runner.start()
    assert runner._thread is not None
    runner._thread.join(timeout=2)
    assert not runner._thread.is_alive()
    expected = [] if failure_stage == 'open' else ['closed']
    assert events == [*expected, f'{failure_stage} failed']


def _score(
    root: Path,
    *,
    start: int = 0,
    channels: list[str] | None = None,
) -> tuple[RecordingScore, AudioStream, np.ndarray]:
    audio = root / 'audio.wav'
    samples = np.column_stack((np.full(48_000, 0.25), np.full(48_000, -0.25)))
    soundfile.write(audio, samples, 48_000, subtype='PCM_16')
    stream = AudioStream(
        name='wide',
        source_id='wide-source',
        source_name='Wide',
        track_name='9-10',
        stream=AudioType(
            timebase='audio', channels=channels or ['input-9', 'input-10']
        ),
        end=start + 48_000,
        fragments=[AudioFragment(asset='audio', start=start, count=48_000)],
        gaps=[Gap(start=0, end=start, reason=GapReason.unknown)] if start else [],
    )
    score = RecordingScore(
        name='recording',
        title='Recording',
        assets=[sealed_asset(audio, root, 'audio', 'wav')],
        timebases=[Timebase(name='audio', rate=Rate(numerator=48_000))],
        body=Recording(state='sealed', streams=[stream]),
    )
    return score, stream, samples
