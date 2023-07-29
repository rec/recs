from functools import cached_property
from . import Array
import dataclasses as dc


@dc.dataclass(frozen=True)
class Block:
    block: Array

    def __len__(self) -> int:
        return self.block.shape[0]

    @cached_property
    def amplitude(self) -> int:
        return self.max - self.min

    @cached_property
    def max(self) -> int:
        return self.block.max()

    @cached_property
    def min(self) -> int:
        return self.block.min()


class Blocks:
    blocks: list[Block] = dc.field(default_factory=list)
    length: int = 0

    def append(self, block):
        self.blocks.append(block)
        self.length += len(block)

    def clear(self):
        self.length = 0
        self.blocks.clear()

    def clip_to_length(self, sample_length: int):
        removed = []
        while self.length > sample_length:
            block = self.blocks.pop(0)
            removed.append(block)
            self.length -= len(block)
        return removed

    def write(self, sf):
        for b in self.blocks:
            sf.write(b)
        self.clear()

    def __getitem__(self, i):
        return self.blocks[i]

    def __len__(self):
        return len(self.blocks)
