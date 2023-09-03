import typing as t

from rich.table import Table as RichTable

from .block import Array, Block
from .device import InputDevice

__all__ = (
    'Array',
    'Block',
    'Callback',
    'SlicesDict',
    'InputDevice',
    'InputDevices',
    'RichTable',
    'Slices',
)

Callback = t.Callable[[Block, str, InputDevice], None]
InputDevices = t.Sequence[InputDevice]
Slices = dict[str, slice]
SlicesDict = dict[str, Slices]
Stop = t.Callable[[], None]
TableMaker = t.Callable[[], RichTable]
