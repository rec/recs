import dataclasses as dc
import time
import typing as t
from copy import deepcopy
from functools import cached_property

import threa
from rich.console import Console
from rich.live import Live
from rich.table import Table

from recs import field
from recs.ui import recorder

from . import device, mux, slicer

FLOW_SLICE = slicer.auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}
CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]


@dc.dataclass
class Monitor(threa.Runnable):
    recorder: recorder.Recorder

    slices: slicer.SlicesDict = field(lambda: deepcopy(DEVICE_SLICES))
    devices: t.Sequence[device.InputDevice] = field(
        lambda: device.input_devices().values()
    )
    refresh_per_second: float = 20
    sleep_time: float = 0.01

    def __post_init__(self):
        super().__init__()

    @cached_property
    def live(self) -> Live:
        table = self.recorder.table()
        return Live(table, refresh_per_second=self.refresh_per_second, console=CONSOLE)

    @cached_property
    def context(self):
        callback = self.recorder.callback
        return mux.DemuxContext(self.devices, callback, self.stop, self.slices)()

    def run(self):
        self.start()
        with self.live, self.context:
            while self.running:
                time.sleep(self.sleep_time)
                self.live.update(self.recorder.table())
