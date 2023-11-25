import typing as t


class ChannelMessage(t.NamedTuple):
    file_count: int = 0
    file_size: int = 0
    is_active: bool = False
    recorded: float = 0
    volume: tuple[float, ...] = ()


DeviceMessages = dict[str, ChannelMessage]
AllMessages = dict[str, DeviceMessages]
