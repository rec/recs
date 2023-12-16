from test.conftest import BLOCK_SIZE, TIMESTAMP
from test.mock_input_stream import InputStreamReporter

from threa import HasThread

from recs.base import times
from recs.cfg import Cfg, run

DEVICE_OFFSET = 0.000_0237


class RecsRunner:
    _time = TIMESTAMP

    def __init__(self, cfg, monkeypatch, event_count):
        import sounddevice as sd

        monkeypatch.setattr(sd, 'InputStream', self.make_input_stream)
        monkeypatch.setattr(times, 'time', self.time)

        self.streams = []
        self.cfg = Cfg(shortest_file_time=0, total_run_time=0.1, **cfg)
        self.event_count = event_count

    def make_input_stream(self, **ka):
        self.streams.append(s := InputStreamReporter(**ka))
        return s

    def events(self):
        for stream in self.streams:
            offset = stream.channels * DEVICE_OFFSET
            block_time = BLOCK_SIZE / stream.samplerate
            blocks = int(2 * self.cfg.total_run_time / block_time)
            for i in range(blocks):
                yield (offset + i * block_time), stream

    def time(self):
        return self._time

    def run(self):
        with HasThread(lambda: run.run(self.cfg)):
            while sum(1 for i in self.events()) < self.event_count:
                times.sleep(0.001)

            for offset, stream in sorted(self.events()):
                if 'stop' not in stream._recs_report:
                    self._time = TIMESTAMP + offset
                    stream._recs_callback()
