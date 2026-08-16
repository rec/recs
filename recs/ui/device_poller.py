import json
import subprocess
import threading
import time
from queue import Empty, Queue
from typing import TypeVar

from threa import HasThread

from recs.base import app_command
from recs.cfg import device

STREAM_TIMEOUT = device.DEVICE_QUERY_TIMEOUT
RESTART_BACKOFF_SECONDS = 1.0
MAX_RESTART_BACKOFF_SECONDS = 30.0
_T = TypeVar('_T')


class DevicePoller(HasThread):
    def __init__(self, interval: float) -> None:
        self.snapshots: Queue[dict[str, device.DeviceDict]] = Queue(maxsize=1)
        self.query_stream = DeviceQueryStream()
        super().__init__(
            self.poll,
            looping=True,
            name='DevicePoller',
            post_delay=interval,
        )

    def start(self) -> None:
        self.query_stream.start()
        super().start()

    def stop(self) -> None:
        self.query_stream.stop()
        super().stop()

    def join(self, timeout: float | None = None) -> None:
        super().join(timeout)
        self.query_stream.stop()

    def poll(self) -> None:
        if (devices := self.query_stream.devices()) is None:
            return
        snapshot = {
            str(info['name']): info for info in devices if info['max_input_channels']
        }
        _put_latest(self.snapshots, snapshot)

    def latest(self) -> dict[str, device.DeviceDict] | None:
        latest = None
        try:
            while True:
                latest = self.snapshots.get_nowait()
        except Empty:
            return latest


class DeviceQueryStream:
    def __init__(self) -> None:
        self.updates: Queue[list[device.DeviceDict]] = Queue(maxsize=1)
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.last_update = time.monotonic()
        self.last_exitcode: int | None = None
        self.next_start = 0.0
        self.restart_backoff = RESTART_BACKOFF_SECONDS

    def start(self) -> None:
        if self.process is not None:
            return
        if time.monotonic() < self.next_start:
            return
        self.process = subprocess.Popen(
            app_command.command('query-devices-stream'),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        self.last_update = time.monotonic()
        self.reader = threading.Thread(
            target=self._read,
            daemon=True,
            name='QueryDevices',
        )
        self.reader.start()

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(STREAM_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        if self.process.stdout is not None:
            self.process.stdout.close()
        self.last_exitcode = self.process.poll()
        self.process = None
        self.reader = None

    def devices(self) -> list[device.DeviceDict] | None:
        latest = None
        try:
            while True:
                latest = self.updates.get_nowait()
        except Empty:
            pass
        if latest is not None:
            self.last_update = time.monotonic()
            self.next_start = 0.0
            self.restart_backoff = RESTART_BACKOFF_SECONDS
            return latest
        self.start()
        if self.process is None:
            return None
        if self._needs_restart():
            self.restart()
        return None

    def restart(self) -> None:
        self.stop()
        self.next_start = time.monotonic() + self.restart_backoff
        self.restart_backoff = min(
            MAX_RESTART_BACKOFF_SECONDS,
            2 * self.restart_backoff,
        )
        self.start()

    def _needs_restart(self) -> bool:
        if self.process is None or self.process.poll() is not None:
            return True
        return time.monotonic() - self.last_update > STREAM_TIMEOUT

    def _read(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        for line in self.process.stdout:
            try:
                _put_latest(self.updates, json.loads(line))
            except json.JSONDecodeError:
                continue


def _put_latest(queue: Queue[_T], value: _T) -> None:
    try:
        while True:
            queue.get_nowait()
    except Empty:
        pass
    queue.put_nowait(value)
