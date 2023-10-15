from pathlib import Path

import tdir

from recs.recs import Recs


@tdir
def test_end_to_end(mock_devices):
    Recs(
        quiet=True,
        total_run_time=0.1,
    )()

    assert sorted(Path().iterdir()) == []
