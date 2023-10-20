import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.cli import recs

from .conftest import DEVICES

TESTDATA = Path(__file__).parent / 'testdata' / 'end_to_end'


@pytest.mark.parametrize('quiet', (True, False))
@tdir
def test_end_to_end(quiet, mock_devices):
    recs(
        quiet=quiet,
        total_run_time=0.1,
    )

    actual = sorted(Path().glob('*.flac'))
    expected = sorted(TESTDATA.glob('*.flac'))

    if not expected:
        for a in actual:
            (TESTDATA / a).write_bytes(a.read_bytes())
        return

    assert [p.name for p in actual] == [p.name for p in expected]

    ae = zip(actual, expected)
    nae = [(a.name, sf.read(a)[0], sf.read(e)[0]) for a, e in ae]

    [(n, a.shape, e.shape) for n, a, e in nae]
    ds = [(n, a.shape, e.shape) for n, a, e in nae if a.shape != e.shape]
    assert ds == []

    differs_contents = [n for n, a, e in nae if not np.allclose(a, e)]
    assert differs_contents == []


def test_info(mock_devices, capsys):
    recs(info=True)
    actual = json.loads(capsys.readouterr().out)
    assert actual == DEVICES
