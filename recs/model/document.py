"""Common document header. Domain bodies add their own required fields."""

from typing import Literal

from pydantic import Field

from .base import Model


class Document(Model):
    format: Literal['recs'] = 'recs'
    version: Literal[1] = 1
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
