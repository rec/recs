import dataclasses as dc
import time
import typing as t
from copy import deepcopy
from functools import cached_property

from rich.console import Console
from rich.live import Live
from rich.table import Table
from threa import Runnable

from recs import field, recs, split
from recs.audio import device, file_opener, slicer, times
from recs.audio.file_types import Format, Subtype

from .exclude_include import ExcludeInclude

if t.TYPE_CHECKING:
    from .recorder import Recorder

# TODO: this is hardcoded for my system  :-)
FLOW_SLICE = slicer.auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}

CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]

FIELDS = tuple(f.name for f in dc.fields(times.Times))


@dc.dataclass
class Session(Runnable):
    recording: recs.Recording
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
    def exclude_include(self) -> ExcludeInclude:
        r = self.recording
        return ExcludeInclude(r.exclude, r.include)  # type: ignore[attr-defined]

    @cached_property
    def recorder(self) -> 'Recorder':
        from recs.ui.recorder import Recorder

        return Recorder(self)

    def __post_init__(self) -> None:
        super().__init__()

    @cached_property
    def format(self) -> Format:
        format = self.recording.format.upper()  # type: ignore[attr-defined]
        return Format[format or 'none']

    @cached_property
    def subtype(self) -> Subtype:
        subtype = self.recording.subtype.upper()  # type: ignore[attr-defined]
        return Subtype[subtype or 'none']

    @cached_property
    def live(self) -> Live:
        table = self.recorder.table()
        refresh = self.recording.ui_refresh_rate  # type: ignore[attr-defined]
        return Live(
            table,
            console=CONSOLE,
            refresh_per_second=refresh,
            transient=not self.recording.retain,  # type: ignore[attr-defined]
        )

    def run(self) -> None:
        self.start()
        with self.live, self.recorder.context():
            while self.running:
                time.sleep(self.recording.sleep_time)  # type: ignore[attr-defined]
                self.live.update(self.recorder.table())

    def times(self, samplerate: float) -> times.Times[int]:
        s = times.Times(**{k: getattr(self.recording, k) for k in FIELDS})
        return times.scale(s, samplerate)

    def opener(self, channels: int, samplerate: int) -> file_opener.FileOpener:
        return file_opener.FileOpener(
            channels=channels,
            format=self.format,
            samplerate=samplerate,
            subtype=self.subtype,
        )
