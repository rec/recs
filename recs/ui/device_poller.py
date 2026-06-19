from queue import Empty, Queue

from threa import HasThread

from recs.cfg import device


class DevicePoller(HasThread):
    def __init__(self, interval: float) -> None:
        self.snapshots: Queue[dict[str, device.DeviceDict]] = Queue()
        super().__init__(
            self.poll,
            looping=True,
            name='DevicePoller',
            post_delay=interval,
        )

    def poll(self) -> None:
        devices = device.query_devices()
        snapshot = {
            str(info['name']): info
            for info in devices
            if info['max_input_channels']
        }
        self.snapshots.put(snapshot)

    def latest(self) -> dict[str, device.DeviceDict] | None:
        latest = None
        try:
            while True:
                latest = self.snapshots.get_nowait()
        except Empty:
            return latest
