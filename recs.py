from functools import cached_property
import dataclasses as dc
import dtyper as typer
import numpy as np
import sounddevice as sd
import soundfile as sf
import sys
import typing as t

DType = np.int32
Array = np.ndarray


@dc.dataclass
class Block:
    block: Array

    def __post_init__(self):
        self.sample_count, self.channel_count = self.block.shape

    @cached_property
    def amplitude(self) -> DType:
        return self.block.max() - self.block.min()


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

    def __call__(self, listener):
        blocks = listener._blocks

        if block and blocks[-1].amplitude >= self.noise_floor:
            if listener._fp:
                blocks = blocks[:]
            else:
                blocks = blocks[-(self.at_start + 1):]
            listener.blocks.clear()
            listener.record(blocks)

        elif len(blocks) > self.before_splitting:
            listener.close()
            blocks[:] = blocks[-max(self.at_start, 1):]


@dc.dataclass
class ChannelListener:
    channel_slice: slice
    name: str
    path: Path
    samplerate: int
    silence_strategy: SilenceStrategy

    file_suffix: str = '.flac'
    subtype: str = 'PCM_24'

    _blocks: list[Block] = dc.field(default_factory=list)
    _sf: sf.SoundFile | None = None

    def __callback__(self, frames: Array):
        self._blocks.append(Block(frames[, self.channel_slice]))
        self.silence_strategy(self)

    def record(self, blocks):
        self._sf = self._sf or sf.SoundFile(
            self._new_filename(),
            channels=len(self.channel_slice),
            mode='x',
            samplerate=self.samplerate,
            subtype=self.subtype,
        )
        for b in self.blocks:
            self._sf.write(b)

    def close(self):
        if self._sf:
            blocks = self._blocks[:self.silence.at_end]
            self._blocks = self._blocks[self.silence.at_end:]
            self.record(blocks)
            self._sf.close()
            self._sf = None

    def _new_filename(self):
        Path(self.name).mkdir(exist_ok=True)
        ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        return self.path / f'{self.name}-{ts}{self.file_suffix}'


@dc.dataclasses
class Universe:
    device: Device


"""
"""
