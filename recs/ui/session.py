import dataclasses as dc
import time
import typing as t
from functools import cached_property

from rich.console import Console
from rich.live import Live
from rich.table import Table
from threa import Runnable

from recs import recs
from recs.audio import device, file_opener, slicer, times
from recs.audio.file_types import DType, Format, Subtype
from recs.audio.slicer import SlicesDict

from .exclude_include import ExcludeInclude, split_all

if t.TYPE_CHECKING:
    from .recorder import Recorder

# TODO: this is hardcoded for my system  :-)
FLOW_SLICE = slicer.auto_slice(8) | {'Main': slice(8, 10)}
DEVICE_SLICES = {'FLOW': FLOW_SLICE}

CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]
Aliases = dict[str, tuple[str, str]]
AliasesInv = dict[tuple[str, str], list[str]]

FIELDS = tuple(f.name for f in dc.fields(times.Times))


@dc.dataclass
class Session(Runnable):
    recording: recs.Recording
    slices: SlicesDict = dc.field(default_factory=lambda: SlicesDict(DEVICE_SLICES))

    @cached_property
    def aliases(self) -> Aliases:
        aliases_flag = self.recording.alias  # type: ignore[attr-defined]

        def split(name):
            alias, sep, value = (n.strip() for n in name.partition('='))
            return alias, (value or alias)

        aliases, values = zip(*(split(n) for n in aliases_flag))
        if len(set(aliases)) < len(aliases):
            raise ValueError(f'Duplicates in alias names: {aliases}')

        return dict(sorted(zip(aliases, split_all(values))))

    @cached_property
    def aliases_inv(self) -> AliasesInv:
        d: AliasesInv = {}
        for k, v in self.aliases.items():
            d.setdefault(v, []).append(k)
        return d

    @cached_property
    def device_slices(self) -> slicer.SlicesDict:
        # TODO: somehow get from user, as part of aliases maybe?
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
    def dtype(self) -> DType:
        dtype = self.recording.dtype.lower()  # type: ignore[attr-defined]
        return DType[dtype]

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
