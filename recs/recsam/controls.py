"""Named expression domains, independent of any controller protocol."""

from pydantic import model_validator
from typing_extensions import Self

from .base import Bipolar, Model
from .enums import Polarity


class Control(Model):
    polarity: Polarity = Polarity.unipolar
    default: Bipolar = 0.0

    @model_validator(mode='after')
    def valid_default(self) -> Self:
        self.validate_value(self.default)
        return self

    def validate_value(self, value: float) -> None:
        minimum = -1.0 if self.polarity == Polarity.bipolar else 0.0
        if not minimum <= value <= 1.0:
            raise ValueError(f'{self.polarity} control value must be in [{minimum}, 1]')
