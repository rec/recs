from functools import cached_property
import datetime.datetime as dt
import dataclasses as dc
import dtyper as typer
import numpy as np
import sounddevice as sd
import soundfile as sf
import sys
import typing as t

DType = np.int32
Array = np.ndarray


@dc.dataclasses
class Device:
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
            dtype=DType,
            samplerate=self.samplerate,
        )


@dc.dataclass(frozen=True)
class Block:
    block: Array

    def __len__(self) -> int:
        return self.block.shape[0]

    @cached_property
    def amplitude(self) -> DType:
        return self.block.max() - self.block.min()


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


@dc.dataclass
class SilenceStrategy:
    at_start: int
    at_end: int
    before_splitting: int
    noise_floor_db: float = 70
    sample_range: int = 0x1_0000_0000

    @cached_property
    def noise_floor(self):
        ratio = 10 ** (self.noise_floor_db / 10)
        return self.sample_range // ratio


@dc.dataclass
class ChannelListener:
    channel_slice: slice
    name: str
    path: Path
    samplerate: int
    silence: SilenceStrategy

    file_suffix: str = '.flac'
    subtype: str = 'PCM_24'

    _blocks: Blocks = dc.field(default_factory=Blocks)
    _sf: sf.SoundFile | None = None

    def __callback__(self, frames: Array):
        block = Block(frames[, self.channel_slice])
        self._blocks.append(block)

        if block.amplitude >= self.silence.noise_floor:
            if not self._fp:
                self.blocks.clip_to_length(self.at_start + len(block))
            self._record()

        elif blocks.length > self.before_splitting:
            self.close()

    def _record(self):
        self._sf = self._sf or sf.SoundFile(
            self._new_filename(),
            channels=len(self.channel_slice),
            mode='x',
            samplerate=self.samplerate,
            subtype=self.subtype,
        )
        for b in self._blocks:
            self._sf.write(b.block)
        self._blocks.clear()

    def close(self):
        if self._sf:
            blocks = self._blocks[:self.silence.at_end]
            self._blocks = self._blocks[self.silence.at_end:]
            self.record(blocks)
            self._sf.close()
            self._sf = None

    def _new_filename(self):
        filename = str(self.path / f'{self.name}-{ts()}{self.file_suffix}')
        print('Creating', filename)
        return filepath


def ts()
    return dt.now().strftime('%Y%m%d-%H%M%S')


@dc.dataclasses
class Universe:
    device: Device


"""
"""
