"""Pure document values, independent of devices and rendering."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


class Model(BaseModel, frozen=True):
    model_config = ConfigDict(
        extra='forbid', allow_inf_nan=False, validate_default=True
    )


def identifier(value: str) -> str:
    if not value or not value[0].islower():
        raise ValueError('must start with a lowercase letter')
    if any(not (c.islower() or c.isdigit() or c in '-_') for c in value):
        raise ValueError('must contain only lowercase letters, numbers, - or _')
    return value


def unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f'duplicate {label}')


Identifier = Annotated[str, AfterValidator(identifier)]
