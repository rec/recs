from functools import cached_property
import dataclasses as dc
import dtyper as typer
import numpy as np
import typing as t


@dc.dataclass(frozen=True)
class Block:
    block: np.ndarray

    @cached_property
    def amplitude(self):
        return self.block.max() - self.block.min()



"""
for each block:
   three categories: black, quiet, sound


"""
