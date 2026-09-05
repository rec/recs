import numpy as np

from recs.edit.automation import gain_values
from recs.edit.schema import AutomationSpec


def test_gain_values_hold_declared_value_before_first_point() -> None:
    automation = AutomationSpec.model_validate(
        {
            'target': 'clip:voice:gain',
            'interpolation': 'linear',
            'points': [
                {'frame': 2, 'value': 0.0},
                {'frame': 6, 'value': 1.0},
            ],
        }
    )

    np.testing.assert_allclose(
        gain_values(automation, 0.5, 0, 8),
        [0.5, 0.5, 0.0, 0.25, 0.5, 0.75, 1.0, 1.0],
    )


def test_equal_power_automation_interpolates_squared_gain() -> None:
    automation = AutomationSpec.model_validate(
        {
            'target': 'clip:voice:gain',
            'interpolation': 'equal_power',
            'points': [
                {'frame': 0, 'value': 0.0},
                {'frame': 4, 'value': 1.0},
            ],
        }
    )

    np.testing.assert_allclose(
        gain_values(automation, 0.0, 0, 5),
        [0.0, 0.5, np.sqrt(0.5), np.sqrt(0.75), 1.0],
    )
