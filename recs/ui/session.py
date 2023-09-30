import dataclasses as dc
import time
import typing as t
from copy import deepcopy
from functools import cached_property

from rich.console import Console
from rich.live import Live
from rich.table import Table
from threa import Runnable

from recs import cli, field
from recs.audio import device, slicer

if t.TYPE_CHECKING:
    from recs.ui.recorder import Recorder

FLOW_SLICE = slicer.auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}
CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]


@dc.dataclass
class Session(Runnable):
    recording: cli.Recording

    slices: slicer.SlicesDict = field(lambda: deepcopy(DEVICE_SLICES))

    @cached_property
    def devices(self) -> tuple[device.InputDevice, ...]:
        return tuple(device.input_devices().values())

    @property
    def device_slices(self) -> slicer.SlicesDict:
        return {}

    @cached_property
    def recorder(self) -> 'Recorder':
        from recs.ui.recorder import Recorder

        return Recorder(self)

    def __post_init__(self):
        super().__init__()

    @cached_property
    def live(self) -> Live:
        table = self.recorder.table()
        assert hasattr(self.recording, 'ui_refresh_rate')  # Why?!
        return Live(
            table, refresh_per_second=self.recording.ui_refresh_rate, console=CONSOLE
        )

    def run(self):
        self.start()
        with self.live, self.recorder.context():
            while self.running:
                time.sleep(self.recording.sleep_time)
                self.live.update(self.recorder.table())
