from dvice import poller

from recs.base import app_command


class DevicePoller(poller.DevicePoller):
    def __init__(self, interval: float) -> None:
        super().__init__(interval, app_command.command('query-devices-stream'))
