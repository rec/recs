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
from recs.audio.file_types import DType, Format, Subtype

from .exclude_include import DeviceChannel, ExcludeInclude, split_all

if t.TYPE_CHECKING:
    from .recorder import Recorder


CONSOLE = Console(color_system='truecolor')
InputDevice = device.InputDevice
TableMaker = t.Callable[[], Table]

FIELDS = tuple(f.name for f in dc.fields(times.Times))


@dc.dataclass
class Session(Runnable):
    recording: recs.Recording

    @cached_property
    def aliases(self) -> dict[str, DeviceChannel]:
        aliases_flag = self.recording.alias

        def split(name: str) -> tuple[str, str]:
            alias, sep, value = (n.strip() for n in name.partition('='))
            return alias, (value or alias)

        aliases, values = zip(*(split(n) for n in aliases_flag))
        if len(set(aliases)) < len(aliases):
            raise ValueError(f'Duplicates in alias names: {aliases}')

        return dict(sorted(zip(aliases, split_all(values))))

    @cached_property
    def aliases_inv(self) -> dict[DeviceChannel, str]:
        d: dict = {}
        for k, v in self.aliases.items():
            d.setdefault(v, []).append(k)

        if duplicate_aliases := [(k, v) for k, v in d.items() if len(v) > 1]:
            raise ValueError(f'{duplicate_aliases = }')

        return {k: v[0] for k, v in sorted(d.items())}

    @cached_property
    def device_slices(self) -> dict[str, list[DeviceChannel]]:
        def device_slice(d: device.InputDevice) -> t.Iterator[DeviceChannel]:
            yield DeviceChannel('FIXME', str(d.channels))

        return {d.name: list(device_slice(d)) for d in device.input_devices().values()}

    @cached_property
    def exclude_include(self) -> ExcludeInclude:
        r = self.recording
        return ExcludeInclude(r.exclude, r.include)

    @cached_property
    def recorder(self) -> 'Recorder':
        from recs.ui.recorder import Recorder

        return Recorder(self)

    def __post_init__(self) -> None:
        super().__init__()

    @cached_property
    def format(self) -> Format:
        return self.recording.format

    @cached_property
    def subtype(self) -> Subtype | None:
        return self.recording.subtype

    @cached_property
    def dtype(self) -> DType:
        return self.recording.dtype

    @cached_property
    def live(self) -> Live:
        table = self.recorder.table()
        refresh = self.recording.ui_refresh_rate
        return Live(
            table,
            console=CONSOLE,
            refresh_per_second=refresh,
            transient=not self.recording.retain,
        )

    def run(self) -> None:
        self.start()
        with self.live, self.recorder.context():
            while self.running:
                time.sleep(self.recording.sleep_time)
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
