"""Paced synthetic inputs for command-line profiling."""

import os
from collections.abc import Callable
from threading import Event
from time import monotonic, time

import numpy as np
from reccy.device import DeviceDict
from threa import HasThread

from recs.base.types import SdType

from .source import Update

FAKE_DEVICES_ENV = 'RECS_PROFILE_FAKE_DEVICES'
SAMPLE_RATE = 48_000
CALLBACK_FRAMES = 960


def device_channels(spec: str) -> list[int]:
    if not spec or any(
        not p.isascii() or not p.isdecimal() or int(p) <= 0 for p in spec.split(':')
    ):
        raise ValueError(
            'Fake device spec must contain positive integers '
            'separated by colons, e.g. 18:10'
        )
    return [int(p) for p in spec.split(':')]


def inventory() -> list[DeviceDict] | None:
    spec = os.environ.get(FAKE_DEVICES_ENV)
    if spec is None:
        return None
    return [
        {
            'name': f'Profile fake {i + 1}',
            'max_input_channels': c,
            'default_samplerate': SAMPLE_RATE,
            'max_output_channels': 0,
        }
        for i, c in enumerate(device_channels(spec))
    ]


class FakeInputStream(HasThread):
    def __init__(
        self,
        channels: int,
        sdtype: SdType,
        callback: Callable[[Update], None],
        blocksize: int | None = None,
    ) -> None:
        self.cancelled = Event()
        self.channels = channels
        self.sdtype = sdtype
        self.update = callback
        self.frames = blocksize or CALLBACK_FRAMES
        super().__init__(self.capture, daemon=True)

    def stop(self) -> None:
        self.cancelled.set()
        super().stop()

    def capture(self) -> None:
        start = time()
        deadline = monotonic()
        cursor = 0
        frequencies = np.arange(self.channels) + 220
        while not self.cancelled.is_set():
            positions = np.arange(cursor, cursor + self.frames) / SAMPLE_RATE
            samples = 0.1 * np.sin(2 * np.pi * positions[:, None] * frequencies)
            dtype = np.dtype(self.sdtype)
            if dtype.kind == 'i':
                samples *= 1 << (8 * dtype.itemsize - 1)
            self.update(Update(samples.astype(dtype), start + cursor / SAMPLE_RATE))
            cursor += self.frames
            deadline += self.frames / SAMPLE_RATE
            self.cancelled.wait(max(0, deadline - monotonic()))
