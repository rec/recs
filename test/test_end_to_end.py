import json
from pathlib import Path

import numpy as np
import pytest
import soundfile
import tdir

from recs.base.types import Format
from recs.cfg import Cfg, run_cli

from .conftest import DEVICES
from .recs_runner import RecsRunner

EVENT_COUNT = 218
EVENT_COUNT_SINGLE = 75


TESTDATA = Path(__file__).parent / 'testdata/end_to_end'

CASES = (
    ('default', {}, EVENT_COUNT),
    ('default', {'dry_run': True, 'silent': True}, EVENT_COUNT),
    ('single', {'include': ['flow'], 'silent': True}, EVENT_COUNT_SINGLE),
    ('time', {'output_directory': '{sdate}', 'silent': True}, EVENT_COUNT),
    (
        'device_channel',
        {'output_directory': '{device}/{channel}', 'silent': True},
        EVENT_COUNT,
    ),
)


@pytest.mark.parametrize('name, cfg, event_count', CASES)
@tdir
def test_end_to_end(name, cfg, event_count, mock_mp, mock_devices, monkeypatch):
    test_case = RecsRunner(cfg, monkeypatch, event_count)
    test_case.run()

    events = sorted(test_case.events())
    events = [(int(o * 1_000_000), s.channels) for o, s in events]
    assert len(events) == event_count

    actual = sorted(Path().glob(f'**/*.{Format._default}'))

    if test_case.cfg.dry_run:
        assert not actual
        return

    tdata = TESTDATA / name
    expected = sorted(tdata.glob(f'**/*.{Format._default}'))

    if not expected:
        for a in actual:
            f = tdata / a
            f.parent.mkdir(exist_ok=True, parents=True)
            f.write_bytes(a.read_bytes())
        return

    assert actual == [p.relative_to(tdata) for p in expected]
    assert [p.name for p in actual] == [p.name for p in expected]

    ae = list(zip(actual, expected, strict=False))

    nae = [(a.name, soundfile.read(a)[0], soundfile.read(e)[0]) for a, e in ae]
    ds = [(n, a.shape, e.shape) for n, a, e in nae if a.shape != e.shape]
    assert ds == []

    differs_contents = [n for n, a, e in nae if not np.allclose(a, e)]
    assert differs_contents == []

    # Exact equality!
    contents = [(a, e) for a, e in ae if a.read_bytes() != e.read_bytes()]
    if not contents:
        return


def test_info(mock_input_streams, capsys):
    run_cli.run_cli(Cfg(info=True))
    data = capsys.readouterr().out

    actual = json.loads(data)
    assert actual == DEVICES
