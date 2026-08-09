import json
import subprocess
import threading
import time
from queue import Empty, Queue

from threa import HasThread

from recs.base import app_command
from recs.cfg import device

STREAM_TIMEOUT = device.DEVICE_QUERY_TIMEOUT


class DevicePoller(HasThread):
    def __init__(self, interval: float) -> None:
        self.snapshots: Queue[dict[str, device.DeviceDict]] = Queue()
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
        self.snapshots.put(snapshot)

    def latest(self) -> dict[str, device.DeviceDict] | None:
        latest = None
        try:
            while True:
                latest = self.snapshots.get_nowait()
        except Empty:
            return latest


class DeviceQueryStream:
    def __init__(self) -> None:
        self.updates: Queue[list[device.DeviceDict]] = Queue()
        self.process: subprocess.Popen[str] | None = None
        self.reader: threading.Thread | None = None
        self.last_update = time.monotonic()

    def start(self) -> None:
        if self.process is not None:
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
        self.process = None
        self.reader = None

    def devices(self) -> list[device.DeviceDict] | None:
        self.start()
        latest = None
        try:
            while True:
                latest = self.updates.get_nowait()
        except Empty:
            pass
        if latest is not None:
            self.last_update = time.monotonic()
            return latest
        if self._needs_restart():
            self.restart()
        return None

    def restart(self) -> None:
        self.stop()
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
                self.updates.put(json.loads(line))
            except json.JSONDecodeError:
                continue
