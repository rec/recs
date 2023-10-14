import dataclasses as dc
import time
import typing as t
from functools import cached_property

from rich.console import Console
from rich.live import Live
from rich.table import Table
from threa import Runnable

from recs import recs
from recs.audio import device, file_opener, times

from .aliases import Aliases
from .exclude_include import ExcludeInclude

if t.TYPE_CHECKING:
    from .recorder import Recorder


CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]

FIELDS = tuple(f.name for f in dc.fields(times.Times))


@dc.dataclass
class Session(Runnable):
    recs: recs.Recs

    @cached_property
    def aliases(self) -> Aliases:
        return Aliases(self.recs.alias)

    @cached_property
    def exclude_include(self) -> ExcludeInclude:
        return ExcludeInclude(self.recs.exclude, self.recs.include)

    @cached_property
    def recorder(self) -> 'Recorder':
        from recs.ui.recorder import Recorder

        return Recorder(self)

    def __post_init__(self) -> None:
        super().__init__()

    @cached_property
    def live(self) -> Live:
        return Live(
            self.recorder.table(),
            console=CONSOLE,
            refresh_per_second=self.recs.ui_refresh_rate,
            transient=not self.recs.retain,
        )

    def run(self) -> None:
        self.start()
        with self.live, self.recorder.context():
            while self.running:
                time.sleep(self.recs.sleep_time)
                self.live.update(self.recorder.table())

    def times(self, samplerate: float) -> times.Times[int]:
        s = times.Times(**{k: getattr(self.recs, k) for k in FIELDS})
        return times.scale(s, samplerate)

    def opener(self, channels: int, samplerate: int) -> file_opener.FileOpener:
        return file_opener.FileOpener(
            channels=channels,
            format=self.recs.format,
            samplerate=samplerate,
            subtype=self.recs.subtype,
        )
