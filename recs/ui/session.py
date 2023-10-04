import dataclasses as dc
import time
import typing as t
from copy import deepcopy
from functools import cached_property

from rich.console import Console
from rich.live import Live
from rich.table import Table
from threa import Runnable

from recs import cli, field, split
from recs.audio import device, file_opener, silence, slicer

from .exc_inc import ExcInc

if t.TYPE_CHECKING:
    from .recorder import Recorder

# TODO: this is hardcoded for my system of course. :-)
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
    def device_names(self) -> dict[str, str]:
        device_names = self.recording.device_names  # type: ignore[attr-defined]
        device_names = (s for d in device_names for s in split(d))
        return {device.input_devices()[k].name: k for k in device_names}

    @cached_property
    def device_slices(self) -> slicer.SlicesDict:
        return slicer.SlicesDict()

    @cached_property
    def exc_inc(self) -> ExcInc:
        r = self.recording
        return ExcInc(r.exclude, r.include)  # type: ignore[attr-defined]

    @cached_property
    def recorder(self) -> 'Recorder':
        from recs.ui.recorder import Recorder

        return Recorder(self)

    def __post_init__(self) -> None:
        super().__init__()

    @cached_property
    def live(self) -> Live:
        table = self.recorder.table()
        refresh = self.recording.ui_refresh_rate  # type: ignore[attr-defined]
        return Live(table, refresh_per_second=refresh, console=CONSOLE)

    def run(self) -> None:
        self.start()
        with self.live, self.recorder.context():
            while self.running:
                time.sleep(self.recording.sleep_time)  # type: ignore[attr-defined]
                self.live.update(self.recorder.table())

    def silence(self, samplerate: float) -> silence.SilenceStrategy[int]:
        fields = [f.name for f in dc.fields(silence.SilenceStrategy)]
        s = silence.SilenceStrategy(**{k: getattr(self.recording, k) for k in fields})
        return silence.scale(s, samplerate)

    def opener(self, channels: int, samplerate: int) -> file_opener.FileOpener:
        return file_opener.FileOpener(
            format=self.recording.format,  # type: ignore[attr-defined]
            subtype=self.recording.subtype,  # type: ignore[attr-defined]
            channels=channels,
            samplerate=samplerate,
        )
