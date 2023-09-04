import dataclasses as dc
import time
from copy import deepcopy
from functools import cached_property

from rich.console import Console
from rich.live import Live

from recs import field
from recs.util import threads, types

from . import device, mux

FLOW_SLICE = mux.auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}
CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice


@dc.dataclass
class Monitor(threads.IsRunning):
    callback: types.Callback
    table_maker: types.TableMaker

    slices: types.SlicesDict = field(lambda: deepcopy(DEVICE_SLICES))
    devices: types.InputDevices = field(lambda: device.input_devices().values())
    refresh_per_second: float = 20
    sleep_time: float = 0.01

    @cached_property
    def live(self) -> Live:
        table = self.table_maker()
        return Live(table, refresh_per_second=self.refresh_per_second, console=CONSOLE)

    @cached_property
    def context(self):
        return mux.demux_context(self.devices, self.callback, self.stop, self.slices)

    def run(self):
        self.start()
        with self.live, self.context:
            while self.running:
                time.sleep(self.sleep_time)
                self.live.update(self.table_maker())
