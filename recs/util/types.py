import typing as t

from rich.table import Table

from recs.audio.block import Array, Block
from recs.audio.device import InputDevice

__all__ = (
    'Array',
    'Block',
    'Callback',
    'InputDevice',
    'InputDevices',
    'Table',
)

Callback = t.Callable[[Block, str, InputDevice], None]
InputDevices = t.Sequence[InputDevice]

Stop = t.Callable[[], None]
TableMaker = t.Callable[[], Table]
