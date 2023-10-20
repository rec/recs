import contextlib
import dataclasses as dc
import time
import typing as t

from rich.table import Table
from threa import Runnable

from recs import recs
from recs.audio import device, file_opener, times

from .. import RecsError
from .aliases import Aliases
from .live import Live

InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]

FIELDS = tuple(f.name for f in dc.fields(times.Times))


class Recorder(Runnable):
    def __init__(self, recs: recs.Recs) -> None:
        from .device_recorder import DeviceRecorder

        super().__init__()

        self.recs = recs
        self.start_time = time.time()
        self.aliases = Aliases(self.recs.alias)
        self.live = Live(self.recs, self.rows)

        devices = device.input_devices().values()
        ie_devices = devices  # TODO
        recorders = (dr for d in ie_devices if (dr := DeviceRecorder(d, self)))
        self.device_recorders = tuple(recorders)

        if not self.device_recorders:
            raise RecsError('No devices or channels selected!')

        self.start()

    def times(self, samplerate: float) -> times.Times[int]:
        s = times.Times(**{k: getattr(self.recs, k) for k in FIELDS})
        return s.scale(samplerate)

    def opener(self, channels: int, samplerate: int) -> file_opener.FileOpener:
        return file_opener.FileOpener(
            channels=channels,
            format=self.recs.format,
            samplerate=samplerate,
            subtype=self.recs.subtype,
        )

    def run(self) -> None:
        self.start()
        with self.context():
            while self.running:
                time.sleep(self.recs.sleep_time)
                self.live.update()

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {'time': f'{self.elapsed_time:9.3f}'}
        for v in self.device_recorders:
            yield from v.rows()

    @contextlib.contextmanager
    def context(self) -> t.Generator:
        try:
            with contextlib.ExitStack() as stack:
                for d in self.device_recorders:
                    stack.enter_context(d.input_stream)
                stack.enter_context(self.live.context())
                yield
        finally:
            self.stop()

    def on_stopped(self) -> None:
        if self.running and all(d.stopped for d in self.device_recorders):
            self.stop()

    def stop(self) -> None:
        self.running.clear()
        for d in self.device_recorders:
            d.stop()
        self.stopped.set()
