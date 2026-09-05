"""Normalize disk thresholds that may be durations or capacities."""

import re
from decimal import Decimal
from math import isfinite

from reccy.configuration.units import magnitude


def normalize(value: str) -> str:
    value = value.strip()
    if LEGACY_MINUTES.fullmatch(value):
        value = value[:-1] + 'min'

    if NUMBER.fullmatch(value):
        amount = Decimal(value)
        is_time = False
    else:
        try:
            amount = Decimal(str(magnitude(value, 'second')))
            is_time = True
        except ValueError:
            try:
                amount = Decimal(str(magnitude(value, 'byte')))
                is_time = False
            except ValueError as error:
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


NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
LEGACY_MINUTES = re.compile(r'\d+(?:\.\d+)?m')
