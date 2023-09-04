import typing as t

from rich.table import Table

from recs.audio.block import Array, Block
from recs.audio.device import InputDevice

__all__ = (
    'Array',
    'Block',
    'Callback',
    'SlicesDict',
    'InputDevice',
    'InputDevices',
    'Slices',
    'Table',
)

Callback = t.Callable[[Block, str, InputDevice], None]
InputDevices = t.Sequence[InputDevice]
Slices = dict[str, slice]
SlicesDict = dict[str, Slices]
Stop = t.Callable[[], None]
TableMaker = t.Callable[[], Table]
