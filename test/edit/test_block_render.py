import gc
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
import soundfile
from ufor.arrangement import ArrangementScore
from ufor.interface import NormalizeMode, OutputSelection

from recs.edit import materialized
from recs.edit.automation import gain_values
from recs.edit.graph import validate_graph
from recs.edit.record import AudioFragment, ResolvedSource
from recs.edit.render import Renderer
from recs.edit.schema import parse_edit
from test.edit.test_schema import COMPLETE_EDIT


@pytest.mark.parametrize('block_frames', [997, 8192, 65_536])
@pytest.mark.parametrize('normalization', list(NormalizeMode))
def test_block_boundaries_preserve_overlap_automation_crop_and_normalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    block_frames: int,
    normalization: NormalizeMode,
) -> None:
    samples = np.column_stack(
        (
            np.linspace(-2, 3, 144_000, dtype=np.float32),
            np.linspace(1, -2, 144_000, dtype=np.float32),
        )
    )
    path = tmp_path / 'source.wav'
    soundfile.write(path, samples, 48_000, subtype='FLOAT')
    source = ResolvedSource(
        name='voice-source',
        record=None,
        file=path,
        session_id=None,
        selector='voice',
        channels=2,
        sample_rate=48_000,
        timeline_end=144_000,
        fragments=[
            AudioFragment(path=path, start=0, end=60_000, channels=2),
            AudioFragment(
                path=path, start=66_000, end=144_000, channels=2, asset_start=66_000
            ),
        ],
    )
    raw = parse_edit(COMPLETE_EDIT).model_dump()
    raw['body']['clips'][0]['source_end'] = 144_000
    raw['body']['clips'].append(
        dict(
            raw['body']['clips'][0],
            name='overlap',
            source_start=12_345,
            source_end=90_001,
            timeline_start=48_017,
            gain=0.75,
        )
    )
    raw['body']['control_clips'][0].update(source_end=100_001, timeline_start=1234)
    raw['outputs'][0]['binding'].update(
        start=17_003, end=130_777, gain=0.7, normalize=normalization
    )
    raw['outputs'].append(
        dict(
            raw['outputs'][0],
            name='dry',
            binding={'track': 'voice', 'start': 0, 'end': 96_000, 'gain': 2.0},
        )
    )
    edit = ArrangementScore.model_validate(raw)
    sources = {OutputSelection(part='voice-source', output='audio'): source}
    # Independent whole-array arithmetic supplies the old renderer's reference.
    samples[60_000:66_000] = 0
    track = samples.copy()
    track[48_017:125_673] += samples[12_345:90_001] * np.float32(0.75)
    gains = gain_values(
        (edit.body.control_clips[0], edit.body.parts[1].score), 0.5, 0, 144_000
    )
    mix = (track * gains[:, None])[17_003:130_777]
    peak = float(np.max(np.abs(mix)))
    scale = 0.7
    if normalization == NormalizeMode.normalize or (
        normalization == NormalizeMode.limit and peak > 1
    ):
        scale /= peak
    expected = {'mix': mix * np.float32(scale), 'dry': track[:96_000] * np.float32(2)}
    monkeypatch.setattr(materialized, 'BLOCK_FRAMES', block_frames)

    outputs = Renderer(edit, sources, validate_graph(edit, sources)).outputs

    for name, audio in outputs.items():
        actual_path = tmp_path / f'{name}.wav'
        expected_path = tmp_path / f'{name}-expected.wav'
        with soundfile.SoundFile(
            actual_path, 'w', samplerate=48_000, channels=2, subtype='FLOAT'
        ) as fp:
            for block in audio.blocks():
                assert len(block) <= block_frames
                fp.write(block)
        soundfile.write(expected_path, expected[name], 48_000, subtype='FLOAT')
        actual, rate = soundfile.read(actual_path, dtype='float32', always_2d=True)
        reference, reference_rate = soundfile.read(
            expected_path, dtype='float32', always_2d=True
        )
        assert rate == reference_rate == 48_000
        np.testing.assert_array_equal(actual, reference)


def test_hour_long_sparse_timeline_keeps_audio_buffers_bounded(tmp_path: Path) -> None:
    path = tmp_path / 'source.wav'
    samples = np.full((48_000, 2), 0.25, dtype=np.float32)
    soundfile.write(path, samples, 48_000, subtype='FLOAT')
    peaks: list[int] = []
    for seconds in (2, 3600):
        end = seconds * 48_000
        source = ResolvedSource(
            name='voice-source',
            record=None,
            file=path,
            session_id=None,
            selector='voice',
            channels=2,
            sample_rate=48_000,
            timeline_end=end,
            fragments=[
                AudioFragment(path=path, start=end - 48_000, end=end, channels=2)
            ],
        )
        raw = parse_edit(COMPLETE_EDIT).model_dump()
        raw['body']['clips'][0]['source_end'] = end
        raw['body']['control_clips'] = []
        raw['outputs'][0]['binding'].update(start=end - 48_000, end=end)
        edit = ArrangementScore.model_validate(raw)
        sources = {OutputSelection(part='voice-source', output='audio'): source}
        gc.collect()
        tracemalloc.start()
        try:
            renderer = Renderer(edit, sources, validate_graph(edit, sources))
            output = renderer.outputs['mix']
            with soundfile.SoundFile(
                tmp_path / f'{seconds}.wav',
                'w',
                samplerate=48_000,
                channels=2,
                subtype='FLOAT',
            ) as fp:
                for block in output.blocks():
                    fp.write(block)
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
        del output, renderer
    # The old implementation allocates >1 GiB per timeline array here.
    assert max(peaks) < 16 * 1024 * 1024, peaks
    assert peaks[1] < peaks[0] + 1024 * 1024, peaks
    print(f'Traced peak bytes, 2 seconds / 1 hour: {peaks}')
    short, short_rate = soundfile.read(tmp_path / '2.wav', dtype='float32')
    long, long_rate = soundfile.read(tmp_path / '3600.wav', dtype='float32')
    assert short_rate == long_rate == 48_000
    np.testing.assert_array_equal(short, long)


def test_prepared_audio_views_preserve_snapshot_and_native_offsets(
    tmp_path: Path,
) -> None:
    path = tmp_path / 'source.wav'
    samples = np.column_stack((np.zeros(96_000), np.full(96_000, 0.5)))
    soundfile.write(path, samples, 48_000, subtype='FLOAT')
    source = ResolvedSource(
        name='source',
        record=None,
        file=path,
        session_id=None,
        selector='pair',
        channels=2,
        sample_rate=48_000,
        timeline_end=96_000,
        fragments=[AudioFragment(path=path, start=0, end=96_000, channels=2)],
    )
    audio = materialized.materialize_source(source)
    view = materialized.select_channels(
        materialized.select_audio(audio, 48_000, 96_000), [1]
    )
    del audio
    soundfile.write(path, np.zeros((96_000, 2)), 48_000, subtype='FLOAT')
    saved = view.read(48_000, 48_000)
    soundfile.write(tmp_path / 'snapshot.wav', saved, 48_000, subtype='FLOAT')
    assert saved.shape == (48_000, 1)
    np.testing.assert_array_equal(saved, 0.5)
    assert view.start_frame == 48_000
    assert view.end_frame == 96_000
