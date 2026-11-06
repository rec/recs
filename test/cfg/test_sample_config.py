from pathlib import Path
from typing import TYPE_CHECKING

from recs.cfg.settings import Settings
from recs.cfg.time_settings import TimeSettings

if TYPE_CHECKING:
    from reccy.pytest_plugin import SampleConfigRegression


def test_sample_config(sample_config_regression: 'SampleConfigRegression') -> None:
    sample_config_regression(Settings)


def test_sample_time_settings(
    sample_config_regression: 'SampleConfigRegression',
) -> None:
    sample_config_regression(
        TimeSettings[float],
        path=Path(__file__).parents[2] / 'doc' / 'sample-time-settings.toml',
    )
