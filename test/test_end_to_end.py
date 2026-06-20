import json
from pathlib import Path

import pytest
import tdir

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

    if test_case.cfg.dry_run:
        assert not test_case.paths()
        return

    test_case.assert_matches(TESTDATA / name)


def test_info(mock_input_streams, capsys):
    run_cli.run_cli(Cfg(info=True))
    data = capsys.readouterr().out

    actual = json.loads(data)
    assert actual == DEVICES
