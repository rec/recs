import dataclasses as dc
from functools import cached_property

import numpy as np

from . import Array


@dc.dataclass(frozen=True)
class Block:
    block: Array

    def __len__(self) -> int:
        return self.block.shape[0]

    @cached_property
    def channels(self) -> int:
        return self.block.shape[1]

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

    def __getitem__(self, k):
        return Block(self.block[k])


@dc.dataclass
class Blocks:
    blocks: list[Block] = dc.field(default_factory=list)
    length: int = 0

    def append(self, block):
        self.blocks.append(block)
        self.length += len(block)

    def clear(self):
        self.length = 0
        self.blocks.clear()

    def clip_start(self, sample_length: int):
        """Clip to length sample_length by cutting from the start"""
        return list(self._clip(sample_length, True))

    def clip_end(self, sample_length: int):
        """Clip to length sample_length by cutting from the end"""
        return list(self._clip(sample_length, False))

    def _clip(self, sample_length: int, is_start: bool):
        while self.length > sample_length:
            yield (block := self.blocks.pop(0 if is_start else -1))
            self.length -= len(block)

    def write(self, sf):
        for b in self:
            sf.write(b)
        self.clear()

    def __iter__(self):
        return iter(self.blocks)

    def __getitem__(self, i) -> Block:
        return self.blocks[i]

    def __len__(self):
        return len(self.blocks)
