import dataclasses as dc
import typing as t
from functools import cached_property

import numpy as np

_EMPTY_SEEN = False


@dc.dataclass(frozen=True)
class Block:
    block: np.ndarray

    def __post_init__(self) -> None:
        if not self.block.size:
            raise ValueError('Empty block')

        if len(self.block.shape) == 1:
            self.__dict__['block'] = self.block.reshape(*self.block.shape, 1)

    def __len__(self) -> int:
        return self.block.shape[0]

    def __getitem__(self, index: int | slice) -> 'Block':
        return Block(self.block[index])

    @cached_property
    def channel_count(self) -> int:
        return (self.block.shape + (1,))[1]

    @cached_property
    def amplitude(self) -> np.ndarray:
        return (self.max - self.min) / 2

    @cached_property
    def max(self) -> np.ndarray:
        return self.block.max(0)

    @cached_property
    def min(self) -> np.ndarray:
        return self.block.min(0)

    @cached_property
    def rms(self) -> np.ndarray:
        b = self.block.astype(float)
        b *= b
        return np.sqrt(b.mean(0))


@dc.dataclass
class Blocks:
    blocks: list[Block] = dc.field(default_factory=list)
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

    def __iter__(self) -> t.Iterator[Block]:
        return iter(self.blocks)

    def __getitem__(self, i: int) -> Block:
        return self.blocks[i]

    def __len__(self) -> int:
        return len(self.blocks)
