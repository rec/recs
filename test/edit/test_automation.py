import numpy as np
from ufor.arrangement import ControlClip
from ufor.automation import (
    ArrangementGainTarget,
    Automation,
    AutomationScore,
    Interpolation,
    Knot,
    Quantity,
    TimelineCurve,
)
from ufor.control import Scope
from ufor.interface import ControlBinding, ControlType, Output, OutputSelection
from ufor.modulation import Unit
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
