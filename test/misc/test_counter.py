from pathlib import Path

import numpy as np
import pytest
import soundfile

from recs.audio.block import Block
from recs.misc.counter import MovingBlock


@pytest.mark.parametrize('window', [0, 4800, 48_000])
def test_meter_average_matches_its_window_after_repeated_rollovers(
    tmp_path: Path, window: int
) -> None:
    phase = np.arange(48_000) / 48_000
    samples = np.column_stack(
        (phase * np.sin(2 * np.pi * 440 * phase), np.sin(2 * np.pi * 330 * phase))
    ).astype(np.float32)
    soundfile.write(tmp_path / 'meter.wav', samples, 48_000, subtype='FLOAT')
    meter = MovingBlock(window)
    np.testing.assert_array_equal(meter.mean(), [0])
    amplitudes = []
    count = int(0.5 + window / 384)
    for start in range(0, len(samples), 384):
        block = Block(block=samples[start : start + 384])
        meter.accumulate(block)
        amplitudes.append(block.amplitude)
        expected = np.mean(amplitudes[-count:], axis=0) if count else [0]
        np.testing.assert_allclose(meter.mean(), expected, rtol=1e-6)
        np.testing.assert_allclose(meter.mean(), expected, rtol=1e-6)
