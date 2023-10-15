import random
import time
from datetime import datetime, timedelta
from functools import cached_property

import numpy as np
import pytest
import sounddevice as sd
from overrides import override
from threa import HasThread

from recs.audio import channel_writer, device, prefix_dict


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

BASE_TIME = datetime(2023, 10, 15, 16, 49, 21, 502)
TIME = BASE_TIME
DELTA = timedelta(seconds=1)


def now():
    global TIME

    return (TIME := TIME + DELTA)


class InputStream(sd.InputStream):
    def __init__(self, **ka):
        for k, v in ka.items():
            try:
                setattr(self, k, v)
            except AttributeError:
                setattr(self, '_' + k, v)

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
        return random.Random(self.__seed)

    @cached_property
    def __rng(self):
        return np.random.default_rng(self.__seed)

    @cached_property
    def __seed(self) -> int:
        return int.from_bytes(self.device.encode())

    @cached_property
    def __thread(self) -> HasThread:
        return HasThread(self.__callback, looping=True)

    def __callback(self) -> None:
        shape = BLOCK_SIZE, self.channels
        array = np.ones(dtype=self.dtype, shape=shape)
        self.callback(array, BLOCK_SIZE, 0, 0)
        time.sleep(SLEEP_TIME * self.__random.uniform(0.8, 1.2))


@pytest.fixture
def mock_devices(monkeypatch):
    monkeypatch.setattr(channel_writer, 'now', now)
    monkeypatch.setattr(device, 'input_devices', lambda: MOCK_DEVICES)
    monkeypatch.setattr(sd, 'InputStream', InputStream)
