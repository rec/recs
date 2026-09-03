"""Parse configuration units once; validated fields contain ordinary numbers."""

import re
from decimal import Decimal
from functools import cache, partial
from importlib.resources import files
from math import isfinite
from typing import Annotated

from pint import UnitRegistry
from pint.errors import PintError
from pydantic import BeforeValidator, Field

from .times import to_time


def magnitude(value: object, unit: str) -> object:
    if isinstance(value, bool):
        raise ValueError('A quantity cannot be a boolean')
    if not isinstance(value, str):
        return value
    if unit == 'second' and ':' in value:
        return to_time(value)
    match = QUANTITY.fullmatch(value.strip())
    if match is None:
        raise ValueError(f'Expected a number optionally followed by a {unit} unit')
    number, supplied_unit = match.groups()
    if not supplied_unit:
        return Decimal(number)
    try:
        return _registry().Quantity(Decimal(number), supplied_unit).to(unit).magnitude
    except PintError as error:
        raise ValueError(f'Expected {unit}: {error}') from None


def disk_threshold(value: str) -> str:
    """Normalize the existing time-or-capacity setting to seconds or whole bytes."""
    value = value.strip()
    # Disk thresholds historically use m for minutes, not metres.
    if re.fullmatch(r'\d+(?:\.\d+)?m', value):
        value = value[:-1] + 'min'
    match = QUANTITY.fullmatch(value)
    if match is None:
        raise ValueError(f'Invalid disk threshold: {value}')
    number, unit = match.groups()
    if not unit:
        amount = Decimal(number)
        is_time = False
    else:
        try:
            quantity = _registry().Quantity(Decimal(number), unit)
            is_time = quantity.check('[time]')
            amount = quantity.to('second' if is_time else 'byte').magnitude
        except PintError as error:
            raise ValueError(f'Expected a duration or capacity: {error}') from None
    if not amount.is_finite() or amount < 0:
        raise ValueError('Disk thresholds must be finite and non-negative')
    if is_time:
        if not isfinite(float(amount)):
            raise ValueError('Disk durations must fit a finite number of seconds')
        return f'{amount}s'
    if amount != amount.to_integral_value():
        raise ValueError('Disk thresholds must be whole bytes')
    return str(int(amount))


@cache
def _registry() -> UnitRegistry:
    # Define the information dimension before Pint caches default dimensionalities.
    registry = UnitRegistry(None, non_int_type=Decimal, on_redefinition='ignore')
    registry.load_definitions(str(files('pint').joinpath('default_en.txt')))
    # Capacities must not accept angles or other dimensionless quantities.
    registry.define('bit = [information]')
    registry.define('kilobyte = 1000 * byte = kB = KB')
    return registry


QUANTITY = re.compile(
    r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)' r'\s*([A-Za-z\u00b5\u03bc]+)?'
)

Seconds = Annotated[
    float,
    Field(allow_inf_nan=False),
    BeforeValidator(partial(magnitude, unit='second')),
]

Milliseconds = Annotated[int, BeforeValidator(partial(magnitude, unit='millisecond'))]

Hertz = Annotated[
    float, Field(allow_inf_nan=False), BeforeValidator(partial(magnitude, unit='hertz'))
]

Bytes = Annotated[int, BeforeValidator(partial(magnitude, unit='byte'))]
Megabytes = Annotated[int, BeforeValidator(partial(magnitude, unit='megabyte'))]
