import random
import time
from functools import cached_property

import numpy as np
import pytest
import sounddevice as sd
from overrides import override
from threa import HasThread

from recs.audio import device, prefix_dict


def _device(name, channels, samplerate=48_000):
    info = {
        'default_samplerate': samplerate,
        'max_input_channels': channels,
        'name': name,
    }
    return device.InputDevice(info)


EXT = _device('Ext', 2, 44_100)
FLOWER = _device('Flower 8', 10)
MIC = _device('Mic', 1)

MOCK_DEVICES = prefix_dict.PrefixDict({d.name: d for d in (EXT, FLOWER, MIC)})
BLOCK_SIZE = 128
SLEEP_TIME = 0.01


class InputStream(sd.InputStream):
    @override
    def start(self) -> None:
        self.__thread.start()

    @override
    def stop(self, ignore_errors: bool = True) -> None:
        self.__thread.stop()

    @override
    def close(self, ignore_errors: bool = True) -> None:
        self.stop()

    @cached_property
    def __random(self):
        return random.Random(seed=self.seed)

    @cached_property
    def __rng(self):
        return np.random.default_rng(self.seed)

    @cached_property
    def __seed(self) -> int:
        return int.frombytes(self.name.encode())

    @cached_property
    def __thread(self) -> HasThread:
        return HasThread(self.__callback)

    def __callback(self) -> None:
        while self.__thread.running:
            shape = BLOCK_SIZE, self.channels
            self.callback(self.__rng.uniform(-1, 1, dtype=self.dtype, shape=shape))
            time.sleep(SLEEP_TIME * self.__random.uniform(0.8, 1.2))


@pytest.fixture
def mock_devices(monkeypatch):
    monkeypatch.setattr(device, 'input_devices', lambda: MOCK_DEVICES)
    monkeypatch.setattr(sd, 'InputStream', InputStream)
