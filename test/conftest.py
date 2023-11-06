import json
import random
import time
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path

import numpy as np
import pytest
import sounddevice as sd
from overrides import override
from threa import HasThread

from recs.base import to_time

DEVICES_FILE = Path(__file__).parent / 'devices.json'
DEVICES = json.loads(DEVICES_FILE.read_text())

BLOCK_SIZE = 0x80
SLEEP_TIME = 0.00001

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
    monkeypatch.setattr(sd, 'query_devices', query_devices)


@pytest.fixture
def mock_now(monkeypatch, mock_devices):
    monkeypatch.setattr(to_time, 'now', now)


@pytest.fixture
def mock_input_streams(monkeypatch, mock_devices, mock_now):
    monkeypatch.setattr(sd, 'InputStream', InputStream)
