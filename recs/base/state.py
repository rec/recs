import dataclasses as dc
import time

from recs.cfg.time_settings import amplitude_to_db

INF = float('inf')


@dc.dataclass(slots=True)
class ChannelState:
    """Represents the state of a single recording channel"""

    condition: str = 'running'

    file_count: int = 0
    file_size: int = 0

    is_active: bool = False

    max_amp: float = -INF
    min_amp: float = INF

    recorded_time: float = 0
    timestamp: float = dc.field(default_factory=time.time)
    volume: tuple[float, ...] = ()

    replace = dc.replace

    @property
    def amp(self) -> float:
        if self.max_amp == -INF or self.min_amp == INF:
            return 0
        return (self.max_amp - self.min_amp) / 2

    @property
    def db_range(self) -> float:
        return amplitude_to_db(self.amp)

    def __iadd__(self, m: 'ChannelState') -> 'ChannelState':
        self.file_count += m.file_count
        self.file_size += m.file_size
        self.recorded_time += m.recorded_time

        # We copy these three when using +=, but not -=!
        self.condition = m.condition
        self.is_active = m.is_active
        self.timestamp = m.timestamp
        self.volume = m.volume

        self.max_amp = max(self.max_amp, m.max_amp)
        self.min_amp = min(self.min_amp, m.min_amp)

        return self

    def __isub__(self, m: 'ChannelState') -> 'ChannelState':
        self.file_count -= m.file_count
        self.file_size -= m.file_size
        self.recorded_time -= m.recorded_time

        self.max_amp = max(self.max_amp, m.max_amp)
        self.min_amp = min(self.min_amp, m.min_amp)

        return self

    def __add__(self, m: 'ChannelState') -> 'ChannelState':
        x = self.replace()
        x += m
        return x

    def __sub__(self, m: 'ChannelState') -> 'ChannelState':
        x = self.replace()
        x -= m
        return x
