import contextlib
import time
import typing as t
from functools import cached_property

from threa import Runnable

from recs.audio import device

from .. import RecsError
from .device_recorder import DeviceRecorder
from .live import Live
from .session import Session


class Recorder(Runnable):
    def __init__(self, session: Session) -> None:
        super().__init__()

        self.session = session
        self.start_time = time.time()

        devices = device.input_devices().values()
        # ie_devices = (d for d in devices if session.exclude_include(d))
        ie_devices = devices  # TODO
        recorders = (dr for d in ie_devices if (dr := DeviceRecorder(d, session)))
        self.device_recorders = tuple(recorders)

        if not self.device_recorders:
            raise RecsError('No devices or channels selected!')

        for d in self.device_recorders:
            d.stopped.on_set.append(self._on_stopped)

        self.start()

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        yield {'time': f'{self.elapsed_time:9.3f}'}
        for v in self.device_recorders:
            yield from v.rows()

    def update(self) -> None:
        self.live.update()

    @cached_property
    def live(self) -> Live:
        return Live(self.session.recs, self.rows)

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

    def _on_stopped(self) -> None:
        if self.running and all(d.stopped for d in self.device_recorders):
            self.stop()

    def stop(self) -> None:
        self.running.clear()
        for d in self.device_recorders:
            d.stop()
        self.stopped.set()
