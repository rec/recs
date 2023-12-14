import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir
from threa import HasThread

from recs.base import times
from recs.cfg import Cfg, run

from .conftest import DEVICES, TIMESTAMP

TESTDATA = Path(__file__).parent / 'testdata/end_to_end'

CASES = (
    ('simple', {}),
    ('simple', {'dry_run': True, 'silent': True}),
    ('time', {'path': '{sdate}'}),
    ('device_channel', {'path': '{device}/{channel}'}),
)


def time():
    return TIMESTAMP


@pytest.mark.parametrize('name, cfd', CASES)
@tdir
def test_end_to_end(name, cfd, mock_mp, mock_devices, monkeypatch):
    import sounddevice as sd

    from .mock_input_stream import InputStreamReporter, ThreadInputStream

    streams = []

    def make_input_stream1(**ka):
        streams.append(s := ThreadInputStream(**ka))
        return s

    def make_input_stream2(**ka):
        streams.append(s := InputStreamReporter(**ka))
        return s

    monkeypatch.setattr(sd, 'InputStream', make_input_stream1)
    monkeypatch.setattr(times, 'time', time)

    cfg = Cfg(shortest_file_time=0, total_run_time=0.1, **cfd)
    with HasThread(lambda: run.run(cfg)):
        pass

    actual = sorted(Path().glob('**/*.flac'))

    if cfg.dry_run:
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
    contents = [e for a, e in ae if a.read_bytes() != e.read_bytes()]
    assert not contents


def test_info(mock_input_streams, capsys):
    run.run(Cfg(info=True))
    data = capsys.readouterr().out

    actual = json.loads(data)
    assert actual == DEVICES
