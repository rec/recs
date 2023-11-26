import dataclasses as dc
import time


@dc.dataclass(slots=True)
class ChannelState:
    """Represents the state of a single recording channel"""

    file_count: int = 0
    file_size: int = 0
    is_active: bool = False
    recorded_time: float = 0
    timestamp: float = dc.field(default_factory=time.time)
    volume: tuple[float, ...] = ()

    replace = dc.replace

    def __iadd__(self, m: 'ChannelState') -> 'ChannelState':
        self.file_count += m.file_count
        self.file_size += m.file_size
        self.recorded_time += m.recorded_time

        # We copy these three when using +=, but not -=!
        self.is_active = m.is_active
        self.timestamp = m.timestamp
        self.volume = m.volume

        return self

    def __isub__(self, m: 'ChannelState') -> 'ChannelState':
        self.file_count -= m.file_count
        self.file_size -= m.file_size
        self.recorded_time -= m.recorded_time

        return self

    def __add__(self, m: 'ChannelState') -> 'ChannelState':
        x = self.replace()
        x += m
        return x

    def __sub__(self, m: 'ChannelState') -> 'ChannelState':
        x = self.replace()
        x -= m
        return x


DeviceState = dict[str, ChannelState]
RecorderState = dict[str, DeviceState]
