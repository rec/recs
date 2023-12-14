import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir
from threa import HasThread

from recs.base import times
from recs.cfg import Cfg, run

from .conftest import BLOCK_SIZE, DEVICES, TIMESTAMP

TESTDATA = Path(__file__).parent / 'testdata/end_to_end'

CASES = (
    ('simple', {}),
    ('simple', {'dry_run': True, 'silent': True}),
    ('time', {'path': '{sdate}'}),
    ('device_channel', {'path': '{device}/{channel}'}),
)

DEVICE_OFFSET = 0.0073


@pytest.mark.parametrize('name, cfd', CASES)
@tdir
def test_end_to_end(name, cfd, mock_mp, mock_devices, monkeypatch):
    import sounddevice as sd

    from .mock_input_stream import InputStreamReporter, ThreadInputStream

    class TestCase:
        _time = TIMESTAMP

        def __init__(self, monkeypatch):
            monkeypatch.setattr(sd, 'InputStream', self.make_input_stream)
            monkeypatch.setattr(times, 'time', self.time)

            self.streams = []
            self.cfg = Cfg(shortest_file_time=0, total_run_time=0.1, **cfd)

        def make_input_stream(self, **ka):
            s = self.InputStream(**ka)
            self.streams.append(s)
            return s

        def time(self):
            return self._time

        def run(self):
            pass

    class ThreadTestCase(TestCase):
        InputStream = ThreadInputStream

    class ReporterTestCase(TestCase):
        InputStream = InputStreamReporter

        def run(self):
            events = []
            for i, stream in enumerate(self.streams):
                dt = BLOCK_SIZE / stream.samplerate
                offset = i * DEVICE_OFFSET
                n = int(2 * self.cfg.total_run_time / dt)
                events.extend((offset + j * dt, stream) for j in range(n))

            for offset, stream in sorted(events):
                if 'stop' not in stream._recs_report:
                    self._time = TIMESTAMP + offset
                    stream._recs_callback()

    test_case = ThreadTestCase(monkeypatch)

    with HasThread(lambda: run.run(test_case.cfg)):
        test_case.run()

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
    contents = [e for a, e in ae if a.read_bytes() != e.read_bytes()]
    assert not contents


def test_info(mock_input_streams, capsys):
    run.run(Cfg(info=True))
    data = capsys.readouterr().out

    actual = json.loads(data)
    assert actual == DEVICES
