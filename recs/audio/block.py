# mypy: disable-error-code="no-any-return, type-arg"

import numbers
import typing as t
from functools import cached_property

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from recs.cfg.source import to_matrix

_EMPTY_SEEN = False


class Block(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    block: np.ndarray

    @field_validator('block')
    @classmethod
    def validate_block(cls, block: np.ndarray) -> np.ndarray:
        if not block.size:
            raise ValueError('Empty block')
        return to_matrix(block)

    def __len__(self) -> int:
        return self.block.shape[0]

    def __getitem__(self, index: int | slice) -> 'Block':
        return Block(block=self.block[index])

    @cached_property
    def is_float(self) -> bool:
        return not issubclass(self.block.dtype.type, numbers.Integral)

    @cached_property
    def scale(self) -> float:
        if self.is_float:
            return 1
        return float(1 << (8 * self.block.dtype.itemsize - 1))

    @cached_property
    def volume(self) -> float:
        return sum(self.amplitude) / len(self.amplitude)

    @cached_property
    def channel_count(self) -> int:
        return (self.block.shape + (1,))[1]

    @cached_property
    def amplitude(self) -> np.ndarray:
        return (self.max - self.min) / (2 * self.scale)

    @cached_property
    def max(self) -> np.ndarray:
        return self.block.max(0)

    @cached_property
    def min(self) -> np.ndarray:
        return self.block.min(0)

    @cached_property
    def asfloat(self) -> 'Block':
        if self.is_float:
            return self
        b = self.block.astype('double' if self.block.dtype.itemsize > 4 else 'float')
        b /= self.scale
        return Block(block=b)

    @cached_property
    def rms(self) -> np.ndarray:
        b = self.asfloat.block
        if b is self.block:
            b = b * b
        else:
            b *= b
        return np.sqrt(b.mean(0))


class Blocks(BaseModel):
    blocks: list[Block] = Field(default_factory=list)
    duration: int = 0

    def append(self, block: Block) -> None:
        self.blocks.append(block)
        self.duration += len(block)

    def clear(self) -> None:
        self.duration = 0
        self.blocks.clear()

    def clip(self, sample_length: int, from_start: bool) -> t.Sequence[Block]:
        clipped = []
        assert sample_length >= 0
        while self.duration > sample_length:
            clipped.append(self.blocks.pop(0 if from_start else -1))
            self.duration -= len(clipped[-1])
        return clipped

    def __getitem__(self, i: int) -> Block:
        return self.blocks[i]
