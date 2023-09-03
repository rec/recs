import dataclasses as dc
import time
from copy import deepcopy
from functools import cached_property

from rich.console import Console
from rich.live import Live

from . import audio_display, device, field, threads
from .mux import auto_slice, demux_context
from .types import Callback, InputDevices, SlicesDict, TableMaker

FLOW_SLICE = auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}
CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice


def check():
    top = audio_display.Top()
    Monitor(top.callback, top.table).run()


@dc.dataclass
class Monitor(threads.IsRunning):
    callback: Callback
    table_maker: TableMaker

    device_slices: SlicesDict = field(lambda: deepcopy(DEVICE_SLICES))
    devices: InputDevices = field(lambda: device.input_devices().values())
    refresh_per_second: float = 20
    sleep_time: float = 0.01

    @cached_property
    def live(self):
        table = self.table_maker()
        return Live(table, refresh_per_second=self.refresh_per_second, console=CONSOLE)

    @cached_property
    def context(self):
        return demux_context(self.devices, self.callback, self.stop, self.device_slices)

    def run(self):
        self.start()
        with self.live, self.context:
            while self.running:
                time.sleep(self.sleep_time)
                self.live.update(self.table_maker())
