from pathlib import Path
from time import perf_counter

import numpy as np
import pytest
import soundfile
from ufor.arrangement import ControlClip
from ufor.automation import (
    ArrangementGainTarget,
    Automation,
    AutomationScore,
    Interpolation,
    Knot,
    Quantity,
    TimelineCurve,
    evaluate,
)
from ufor.control import Scope
from ufor.interface import ControlBinding, ControlType, Output, OutputSelection
from ufor.modulation import Operation, Unit
from ufor.time import Rate, Timebase

from recs.edit.automation import gain_values


def test_gain_values_hold_declared_value_before_first_knot() -> None:
    result = gain_values(_automation(Interpolation.linear, 2, 6), 0.5, 0, 8)

    assert result.dtype == np.float32
    np.testing.assert_allclose(
        result,
        [0.5, 0.5, 0.0, 0.25, 0.5, 0.75, 1.0, 1.0],
    )


def test_equal_power_automation_interpolates_squared_gain() -> None:
    np.testing.assert_allclose(
        gain_values(_automation(Interpolation.equal_power, 0, 4), 0.0, 0, 5),
        [0.0, 0.5, np.sqrt(0.5), np.sqrt(0.75), 1.0],
    )


@pytest.mark.parametrize('interpolation', list(Interpolation))
@pytest.mark.parametrize('combined', [False, True])
def test_gain_blocks_match_scalar_reference(
    tmp_path: Path, interpolation: Interpolation, combined: bool
) -> None:
    clip, score = _automation(interpolation, 2_003, 30_017)
    clip = clip.model_copy(
        update={'timeline_start': 4_017, 'source_start': 1_003, 'source_end': 40_003}
    )
    if combined:
        curves = [
            TimelineCurve(
                name=name,
                unit=Unit.ratio,
                operation=operation,
                interpolation=Interpolation.hold,
                knots=[Knot(tick=tick, value=value)],
            )
            for name, operation, tick, value in [
                ('a', Operation.add, 8_000, 1e16),
                ('b', Operation.add, 8_000, 0.25),
                ('c', Operation.add, 8_000, -1e16),
                ('d', Operation.multiply, 15_003, 0.75),
                ('e', Operation.multiply, 20_007, 0.5),
            ]
        ]
        score = score.model_copy(
            update={
                'body': score.body.model_copy(
                    update={'curves': score.body.curves + curves}
                )
            }
        )
    expected = np.full(48_000, 0.5, dtype=np.float32)
    for tick in range(
        clip.timeline_start, clip.timeline_start + clip.source_end - clip.source_start
    ):
        expected[tick] = evaluate(
            score, clip.source_start + tick - clip.timeline_start, 0.5
        )
    actual = np.concatenate(
        [
            gain_values((clip, score), 0.5, s, min(997, 48_000 - s))
            for s in range(0, 48_000, 997)
        ]
    )
    for name, samples in [('expected', expected), ('actual', actual)]:
        soundfile.write(tmp_path / f'{name}.wav', samples, 48_000, subtype='FLOAT')
    np.testing.assert_array_equal(actual, expected)


def test_combined_gain_rejects_negative_result() -> None:
    clip, score = _automation(Interpolation.hold, 0, 48_000)
    curve = TimelineCurve(
        name='offset',
        unit=Unit.ratio,
        operation=Operation.add,
        knots=[Knot(tick=0, value=-1.0)],
    )
    score = score.model_copy(
        update={'body': score.body.model_copy(update={'curves': [curve]})}
    )
    with pytest.raises(ValueError, match='gain must be nonnegative'):
        gain_values((clip, score), 0.5, 0, 48_000)


def test_long_gain_lane_matches_scalar_reference(tmp_path: Path) -> None:
    frames = 60 * 48_000
    automation = _automation(Interpolation.linear, 0, frames)
    started = perf_counter()
    expected = np.fromiter(
        (evaluate(automation[1], t, 0.5) for t in range(frames)), dtype=np.float32
    )
    scalar_seconds = perf_counter() - started
    started = perf_counter()
    actual = np.concatenate(
        [
            gain_values(automation, 0.5, s, min(65_536, frames - s))
            for s in range(0, frames, 65_536)
        ]
    )
    vector_seconds = perf_counter() - started
    soundfile.write(tmp_path / 'minute.wav', actual, 48_000, subtype='FLOAT')
    np.testing.assert_array_equal(actual, expected)
    print(
        f'One-minute lane: scalar={scalar_seconds:.3f}s, blocks={vector_seconds:.3f}s'
    )


def _automation(
    interpolation: Interpolation, start: int, end: int
) -> tuple[ControlClip, AutomationScore]:
    return (
        ControlClip(
            name='fade',
            source=OutputSelection(name='fade', output='control'),
            source_start=start,
            source_end=end + 2,
            timeline_start=start,
        ),
        AutomationScore(
            name='fade',
            title='Fade',
            timebases=[Timebase(name='audio', rate=Rate(numerator=48_000))],
            outputs=[
                Output(
                    name='control',
                    stream=ControlType(
                        timebase='audio',
                        quantity='gain',
                        unit=Unit.ratio,
                        scope=Scope.part,
                    ),
                    binding=ControlBinding(),
                )
            ],
            body=Automation(
                target=ArrangementGainTarget(kind='clip', name='voice'),
                scope=Scope.part,
                quantity=Quantity.gain,
                unit=Unit.ratio,
                default=0,
                curves=[
                    TimelineCurve(
                        name='gain',
                        unit=Unit.ratio,
                        interpolation=interpolation,
                        knots=[Knot(tick=start, value=0.0), Knot(tick=end, value=1.0)],
                    )
                ],
            ),
        ),
    )
