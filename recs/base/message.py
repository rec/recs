import dataclasses as dc


@dc.dataclass(slots=True)
class ChannelMessage:
    file_count: int = 0
    file_size: int = 0
    is_active: bool = False
    recorded: float = 0
    volume: tuple[float, ...] = ()

    replace = dc.replace

    def __iadd__(self, m: 'ChannelMessage') -> 'ChannelMessage':
        self.file_count += m.file_count
        self.file_size += m.file_size
        self.recorded += m.recorded

        # We do copy these when using +=
        self.is_active = m.is_active
        self.volume = m.volume

        return self

    def __isub__(self, m: 'ChannelMessage') -> 'ChannelMessage':
        self.file_count -= m.file_count
        self.file_size -= m.file_size
        self.recorded -= m.recorded

        return self

    def __add__(self, m: 'ChannelMessage') -> 'ChannelMessage':
        x = self.replace()
        x += m
        return x

    def __sub__(self, m: 'ChannelMessage') -> 'ChannelMessage':
        x = self.replace()
        x -= m
        return x


DeviceMessages = dict[str, ChannelMessage]
AllMessages = dict[str, DeviceMessages]
