from test.conftest import BLOCK_SIZE, TIMESTAMP
from test.mock_input_stream import InputStreamReporter

from threa import HasThread

from recs.base import times
from recs.cfg import Cfg, run

DEVICE_OFFSET = 0.0007373
EVENT_COUNT = 218


class RecsRunner:
    _time = TIMESTAMP

    def __init__(self, cfg, monkeypatch):
        import sounddevice as sd

        monkeypatch.setattr(sd, 'InputStream', self.make_input_stream)
        monkeypatch.setattr(times, 'time', self.time)

        self.streams = []
        self.cfg = Cfg(shortest_file_time=0, total_run_time=0.1, **cfg)

    def make_input_stream(self, **ka):
        self.streams.append(s := InputStreamReporter(**ka))
        return s

    def events(self):
        for i, stream in enumerate(self.streams):
            dt = BLOCK_SIZE / stream.samplerate
            offset = i * DEVICE_OFFSET
            n = int(2 * self.cfg.total_run_time / dt)
            for j in range(n):
                yield (offset + j * dt), stream

    def time(self):
        return self._time

    def run(self):
        with HasThread(lambda: run.run(self.cfg)):
            while sum(1 for i in self.events()) < EVENT_COUNT:
                times.sleep(0.001)

            for offset, stream in sorted(self.events()):
                if 'stop' not in stream._recs_report:
                    self._time = TIMESTAMP + offset
                    stream._recs_callback()
