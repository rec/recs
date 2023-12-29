from threa import IsThread

from recs.cfg import device


class DeviceNames(IsThread):
    daemon = True
    looping = False

    def __init__(self, pre_delay: float) -> None:
        self.pre_delay = pre_delay
        super().__init__()
        self.callback()

    def callback(self) -> None:
        self.names = device.input_names()
