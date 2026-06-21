import typing as t
from numbers import Real

from humanfriendly import format_size
from pydantic import BaseModel, Field

from recs.base import times
from recs.base.types import Active

COLUMNS = [
    'time',
    'device',
    'channel',
    'on',
    'recorded',
    'file_size',
    'file_count',
    'volume',
]


class Cell(BaseModel):
    text: str = ''
    style: str = ''


class Row(BaseModel):
    cells: list[Cell] = Field(default_factory=list)


class ViewModel(BaseModel):
    columns: list[str] = Field(default_factory=lambda: COLUMNS.copy())
    rows: list[Row] = Field(default_factory=list)


def view_model(rows: t.Iterable[t.Mapping[str, object]]) -> ViewModel:
    return ViewModel(rows=[_row(row) for row in rows])


def _row(row: t.Mapping[str, object]) -> Row:
    unknown = set(row) - set(COLUMNS)
    if unknown:  # pragma: no cover
        raise ValueError(f'{unknown=}')
    return Row(cells=[_cell(row.get(column), column) for column in COLUMNS])


def _cell(value: object, column: str) -> Cell:
    if value is None:
        return Cell()

    if column in {'time', 'recorded'}:
        return Cell(text=_time_to_str(value))
    if column == 'file_size':
        return Cell(text=_naturalsize(value))
    if column == 'channel':
        return Cell(text=_channel(value))
    if column == 'on':
        return _on(value)
    if column == 'volume':
        return _volume(value)
    if column == 'file_count':
        return Cell(text=str(value))
    return Cell(text=str(value))


def _on(value: object) -> Cell:
    if value == Active.active:
        return Cell(text='•', style='active')
    if value == Active.offline:
        return Cell(text='ˣ', style='offline')
    return Cell()


def _volume(value: object) -> Cell:
    s = _number(value)
    if s < 0.001:
        return Cell()
    return Cell(text=to_percent(value), style=_volume_style(s))


def _volume_style(value: float) -> str:
    if value < 1 / 3:
        return 'volume-low'
    return 'volume-high'


def _number(value: object) -> float:
    if isinstance(value, Real):
        return float(value)
    return 0.0


def to_percent(value: object) -> str:
    assert isinstance(value, Real), str(value)
    return f'{value:6.1%}'


def _time_to_str(value: object) -> str:
    assert isinstance(value, Real), str(value)
    if not value:
        return ''
    s = times.to_str(float(value))
    return f'{s:>11}'


def _naturalsize(value: object) -> str:
    assert isinstance(value, Real), str(value)
    if not value:
        return ''

    fs = format_size(value)

    # Fix #97
    numeric, _, unit = fs.partition(' ')
    if unit != 'bytes':
        integer, _, decimal = numeric.partition('.')
        decimal = (decimal + '00')[:2]
        fs = f'{integer}.{decimal} {unit}'

    return f'{fs:>9}'


def _channel(value: object) -> str:
    assert isinstance(value, str), str(value)
    return f' {value} ' if len(value) == 1 else value
