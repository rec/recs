import dataclasses as dc
import time
import typing as t
from copy import deepcopy
from functools import cached_property

from rich.console import Console
from rich.live import Live

from . import audio_display, device, field, mux, threads

FLOW_SLICE = mux.auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}
CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice


def check_old():
    devices = device.input_devices()
    g = audio_display.Global()

    running = threads.IsRunning()
    running.start()

    with mux.demux_context(devices.values(), g.callback, running.stop, DEVICE_SLICES):
        with Live(g.table(), refresh_per_second=4, console=CONSOLE) as live:
            while running.running:
                time.sleep(0.01)
                live.update(g.table())


def check():
    Monitor(audio_display.Global()).run()


@dc.dataclass
class Monitor(threads.IsRunning):
    client: t.Any

    device_slices: dict[str, dict[str, slice]] = field(lambda: deepcopy(DEVICE_SLICES))
    devices: device.InputDevices = field(device.input_devices)
    refresh_per_second: float = 20
    sleep_time: float = 0.01

    @cached_property
    def live(self):
        table = self.client.table()
        return Live(table, refresh_per_second=self.refresh_per_second, console=CONSOLE)

    @cached_property
    def context(self):
        return mux.demux_context(
            self.devices.values(), self.client.callback, self.stop, self.device_slices
        )

    def run(self):
        self.start()
        with self.live, self.context:
            while self.running:
                time.sleep(self.sleep_time)
                self.live.update(self.client.table())
