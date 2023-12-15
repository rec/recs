import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs.cfg import Cfg, run

from .conftest import DEVICES
from .recs_runner import EVENT_COUNT, RecsRunner

TESTDATA = Path(__file__).parent / 'testdata/end_to_end'

CASES = (
    ('simple', {}),
    ('simple', {'dry_run': True, 'silent': True}),
    ('time', {'path': '{sdate}'}),
    ('device_channel', {'path': '{device}/{channel}'}),
)


@pytest.mark.parametrize('name, cfg', CASES)
@tdir
def test_end_to_end(name, cfg, mock_mp, mock_devices, monkeypatch):
    test_case = RecsRunner(cfg, monkeypatch)
    test_case.run()

    events = sorted(test_case.events())
    events = [(int(o * 1_000_000), s.channels) for o, s in events]
    assert len(events) == EVENT_COUNT

    actual = sorted(Path().glob('**/*.flac'))

    if test_case.cfg.dry_run:
        assert not actual
        return

    tdata = TESTDATA / name
    expected = sorted(tdata.glob('**/*.flac'))

    if not expected:
        for a in actual:
            f = tdata / a
            f.parent.mkdir(exist_ok=True, parents=True)
            f.write_bytes(a.read_bytes())
        return

    assert actual == [p.relative_to(tdata) for p in expected]
    assert [p.name for p in actual] == [p.name for p in expected]

    ae = list(zip(actual, expected))
    nae = [(a.name, sf.read(a)[0], sf.read(e)[0]) for a, e in ae]

    [(n, a.shape, e.shape) for n, a, e in nae]
    ds = [(n, a.shape, e.shape) for n, a, e in nae if a.shape != e.shape]
    assert ds == []

    differs_contents = [n for n, a, e in nae if not np.allclose(a, e)]
    assert differs_contents == []

    # Exact equality!
    contents = [(a, e) for a, e in ae if a.read_bytes() != e.read_bytes()]
    if not contents:
        return


def test_info(mock_input_streams, capsys):
    run.run(Cfg(info=True))
    data = capsys.readouterr().out

    actual = json.loads(data)
    assert actual == DEVICES
