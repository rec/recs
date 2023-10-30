import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.recs import run_recs

from .conftest import DEVICES

TESTDATA = Path(__file__).parent / 'testdata/end_to_end'
CASES = (
    ('simple', False, False, ()),
    ('simple', True, True, ()),
    ('time', False, False, ('time',)),
    ('device_channel', False, False, ('device', 'channel')),
)


@pytest.mark.parametrize('path, dry_run, quiet, subs', CASES)
@tdir
def test_end_to_end(path, dry_run, quiet, subs, mock_devices, set_recs):
    set_recs(dry_run=dry_run)
    set_recs(quiet=quiet)
    set_recs(subdirectories=subs)
    set_recs(total_run_time=0.1)

    run_recs()

    actual = sorted(Path().glob('**/*.flac'))

    if dry_run:
        assert not actual
        return

    tdata = TESTDATA / path
    expected = sorted(tdata.glob('*.flac'))

    if not expected:
        for a in actual:
            f = tdata / a
            f.parent.mkdir(exist_ok=True, parents=True)
            f.write_bytes(a.read_bytes())
        return

    assert [p.name for p in actual] == [p.name for p in expected]

    ae = zip(actual, expected)
    nae = [(a.name, sf.read(a)[0], sf.read(e)[0]) for a, e in ae]

    [(n, a.shape, e.shape) for n, a, e in nae]
    ds = [(n, a.shape, e.shape) for n, a, e in nae if a.shape != e.shape]
    assert ds == []

    differs_contents = [n for n, a, e in nae if not np.allclose(a, e)]
    assert differs_contents == []


def test_info(mock_devices, capsys, set_recs):
    set_recs(info=True)
    run_recs()
    data = capsys.readouterr().out

    try:
        actual = json.loads(data)
    except Exception:
        print('-------------------', data, '---------------', sep='\n')
        raise

    assert actual == DEVICES
