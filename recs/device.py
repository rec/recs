from . import DType
from functools import cached_property
from queue import Queue
import dataclasses as dc
import sounddevice as sd
import sys


@dc.dataclass
class Device:
    device: int | str
    queue: Queue = dc.field(default_factory=Queue)
    block_count: int = 0

    @cached_property
    def channels(self) -> int:
        return self.info["max_input_channels"]

    @cached_property
    def info(self):
        return sd.query_devices(self.device, "input")

    @cached_property
    def samplerate(self) -> int:
        return int(self.info["default_samplerate"])

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
