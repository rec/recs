from functools import cached_property
import dataclasses as dc
import dtyper as typer
import numpy as np
import sounddevice as sd
import soundfile as sf
import sys
import typing as t

Int = np.int32
array = np.ndarray


@dc.dataclass
class Block:
    block: array

    def __post_init__(self):
        self.sample_count, self.channel_count = self.block.shape

    @cached_property
    def amplitude(self) -> Int:
        return 0 if self.block is None else self.block.max() - self.block.min()

    def blacken(self):
        if self.amplitude:
            return self
        return Black(self.sample_count, self.channel_count)


@dc.dataclass
class Black:
    sample_count: int = 0
    channel_count: int = 2
    amplitude: int = 0


@dc.dataclass
class ChannelListener:
    channels: slice
    noise_floor_db: float = 70
    blocks: t.List[Block] = dc.field(default_factory=list)

    @cached_property
    def noise_floor(self):
        ratio = 10 ** (self.noise_floor_db / 10)
        return 0x1_0000_0000 // ratio

    def __callback__(self, frames: array):
        block = Block(frames[, self.channels])
        if not block.amplitude:
            block = Black
        elif block.amplitude < self.noise_floor:

    def slice(self, frames: array) -> array:
        if b.shape[0] == self.channel_count:
            assert self.channel_start == 0
            return frames


@dc.dataclass
class SliceRouter:
    slices: t.List[slice] = dc.field(default_factory=list)



@dc.dataclasses
class QueuedDevice:
    device: int | str
    queue: Queue = dc.field(default_factory=Quene)
    block_count: int = 0

    @cached_property
    def channels(self) -> int:
        return self.info['max_input_channels')

    @cached_property
    def info(self):
        return sd.query_devices(self.device, 'input')

    @cached_property
    def samplerate(self) -> int:
        return int(self.info['default_samplerate'])

    def callback(self, indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        self.queue.put(indata.copy())
        self.block_count += 1

    @cached_property
    def input_stream(self):
        return sd.InputStream(
            callback=self.callback,
            channels=self.channels,
            device=self.device,
            samplerate=self.samplerate,
        )





@dc.dataclasses
class Universe:
    device: QueuedDevice


"""
"""
