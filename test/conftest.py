import random
import time
from datetime import datetime, timedelta
from functools import cached_property

import numpy as np
import pytest
import sounddevice as sd
from overrides import override
from threa import HasThread

from recs.audio import device, file_creator, prefix_dict


def _device(name, channels, samplerate=48_000):
    info = {
        'default_samplerate': samplerate,
        'max_input_channels': channels,
        'name': name,
    }
    return device.InputDevice(info)


EXT = _device('Ext', 3, 44_100)
FLOWER = _device('Flower 8', 10)
MIC = _device('Mic', 1)

DEVICES = FLOWER, EXT, MIC

MOCK_DEVICES = prefix_dict.PrefixDict({d.name: d for d in DEVICES})
BLOCK_SIZE = 128
SLEEP_TIME = 0.01

BASE_TIME = datetime(2023, 10, 15, 16, 49, 21, 502)
TIME = BASE_TIME
DELTA = timedelta(seconds=1)


def now():
    global TIME

    if True:
        return TIME
    return (TIME := TIME + DELTA)


class InputStream(sd.InputStream):
    def __init__(self, **ka):
        for k, v in ka.items():
            try:
                setattr(self, k, v)
            except AttributeError:
                setattr(self, '_' + k, v)

        self.__count = 0

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
        return HasThread(self.__callback, looping=True, name=f'Thread-{self.device}')

    @cached_property
    def __array(self) -> np.ndarray:
        shape = BLOCK_SIZE, self.channels

        array = self.__rng.uniform(-1, 1, size=shape)
        assert self.dtype == 'float32'
        assert array.dtype == np.double

        return array.astype(self.dtype)

    def __callback(self) -> None:
        self.callback(self.__array, BLOCK_SIZE, 0, 0)
        time.sleep(SLEEP_TIME * self.__random.uniform(0.8, 1.2))


def query_devices(kind=None):
    import copy

    assert kind is None
    return copy.deepcopy(DEVICES)


@pytest.fixture
def mock_devices(monkeypatch):
    monkeypatch.setattr(device, 'input_devices', lambda: MOCK_DEVICES)
    monkeypatch.setattr(file_creator, 'now', now)
    monkeypatch.setattr(sd, 'InputStream', InputStream)
    monkeypatch.setattr(sd, 'query_devices', query_devices)


DEVICES = [
    {
        "name": "Some output",
        "index": 0,
        "hostapi": 0,
        "max_input_channels": 0,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.009833333333333333,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.019166666666666665,
        "default_samplerate": 48000.0,
    },
    {
        "name": "Flower 8",
        "index": 1,
        "hostapi": 0,
        "max_input_channels": 10,
        "max_output_channels": 4,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.004354166666666667,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.0136875,
        "default_samplerate": 48000.0,
    },
    {
        "name": "Mic",
        "index": 3,
        "hostapi": 0,
        "max_input_channels": 1,
        "max_output_channels": 0,
        "default_low_input_latency": 0.033242630385487526,
        "default_low_output_latency": 0.01,
        "default_high_input_latency": 0.043401360544217685,
        "default_high_output_latency": 0.1,
        "default_samplerate": 44100.0,
    },
    {
        "name": "Ext",
        "index": 5,
        "hostapi": 0,
        "max_input_channels": 2,
        "max_output_channels": 2,
        "default_low_input_latency": 0.01,
        "default_low_output_latency": 0.03333333333333333,
        "default_high_input_latency": 0.1,
        "default_high_output_latency": 0.042666666666666665,
        "default_samplerate": 48000.0,
    },
]
