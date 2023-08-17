from . import audio_display, device, mux, threads
from rich.console import Console
from rich.live import Live
import time

FLOW_SLICE = mux.auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}


def check():
    devices = device.input_devices()
    g = audio_display.Global()
    console = Console(color_system='truecolor')
    running = threads.IsRunning()
    running.start()

    try:
        with mux.demux_context(devices.values(), g, running.stop, DEVICE_SLICES):
            with Live(g.table(), refresh_per_second=4, console=console):
                while running.running:
                    time.sleep(0.01)
    except KeyboardInterrupt:
        pass
