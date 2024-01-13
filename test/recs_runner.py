import traceback
from test.conftest import BLOCK_SIZE, TIMESTAMP
from test.mock_input_stream import InputStreamReporter

from threa import HasThread

from recs.base import times
from recs.cfg import Cfg, run_cli

DEVICE_OFFSET = 0.000_0237
TRIES = 100
DELAY = 0.001


class RecsRunner:
    _timestamp = TIMESTAMP

    def __init__(self, cfg, monkeypatch, event_count):
        import sounddevice as sd

        monkeypatch.setattr(sd, 'InputStream', self.make_input_stream)
        monkeypatch.setattr(times, 'timestamp', self.timestamp)

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

    def timestamp(self):
        return self._timestamp

    def run_cli(self) -> None:
        try:
            run_cli.run_cli(self.cfg)
        except Exception:
            traceback.print_exc()
            self._error = traceback.format_exc()

    def run(self):
        self._error = ''

        with HasThread(self.run_cli, name='RunCli'):
            for i in range(TRIES):
                if (event_count := sum(1 for _ in self.events())) >= self.event_count:
                    break
                times.sleep(DELAY)
            else:
                raise ValueError(f'{event_count=} {self._error=}')

            for offset, stream in sorted(self.events()):
                if 'stop' not in stream._recs_report:
                    self._timestamp = TIMESTAMP + offset
                    stream._recs_callback()
