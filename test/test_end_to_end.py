from pathlib import Path

import numpy as np
import soundfile as sf
import tdir

from recs.recs import Recs

TESTDATA = Path(__file__).parent / 'testdata' / 'end_to_end'


@tdir
def test_end_to_end(mock_devices):
    Recs(
        quiet=True,
        total_run_time=0.1,
    )()

    actual = sorted(Path().glob('*.flac'))
    expected = sorted(TESTDATA.glob('*.flac'))

    if not expected:
        for a in actual:
            (TESTDATA / a).write_bytes(a.read_bytes())

    else:
        assert [p.name for p in actual] == [p.name for p in expected]

        ae = zip(actual, expected)
        nae = [(a.name, sf.read(a)[0], sf.read(e)[0]) for a, e in ae]

        [(n, a.shape, e.shape) for n, a, e in nae]
        ds = [(n, a.shape, e.shape) for n, a, e in nae if a.shape != e.shape]
        assert ds == []

        differs_contents = [n for n, a, e in nae if not np.allclose(a, e)]
        assert differs_contents == []
