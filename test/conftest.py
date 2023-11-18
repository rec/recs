import copy
import json
import random
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path

import numpy as np
import pytest
from threa import HasThread

from recs.base import times
from recs.cfg import device

DEVICES_FILE = Path(__file__).parent / 'devices.json'
DEVICES = json.loads(DEVICES_FILE.read_text())

BLOCK_SIZE = 0x80
SLEEP_TIME = 0.00001

TIME = datetime(2023, 10, 15, 16, 49, 21, 502)
TIMESTAMP = TIME.timestamp()
DELTA = timedelta(seconds=1)


def time():
    return TIMESTAMP


def query_devices(kind=None):
    assert kind is None
    return copy.deepcopy(DEVICES)


@pytest.fixture
def mock_devices(monkeypatch):
    monkeypatch.setattr(device, 'query_devices', query_devices)


@pytest.fixture
def mock_input_streams(monkeypatch, mock_devices):
    import sounddevice as sd

    class InputStream(sd.InputStream):
        BLOCK_SIZE = 0x80

        def __init__(self, **ka):
            for k, v in ka.items():
                try:
                    setattr(self, k, v)
                except AttributeError:
                    setattr(self, '_' + k, v)

            self.__count = 0

            seed = int.from_bytes(self.device.encode(), byteorder='big')
            self.__rng = np.random.default_rng(seed)
            self.__random = random.Random(seed)
            self.__thread = HasThread(
                self.__callback, looping=True, name=f'Thread-{self.device}'
            )

        def start(self) -> None:
            self.__thread.start()

        def stop(self, ignore_errors: bool = True) -> None:
            self.__thread.stop()

        def close(self, ignore_errors: bool = True) -> None:
            self.stop()

        @cached_property
        def __array(self) -> np.ndarray:
            shape = self.BLOCK_SIZE, self.channels

            array = self.__rng.uniform(-1 / 16, 1 / 16, size=shape)
            assert self.dtype == 'float32'
            assert array.dtype == np.double

            return array.astype(self.dtype)

        def __callback(self) -> None:
            self.callback(self.__array, self.BLOCK_SIZE, 0, 0)
            times.sleep(SLEEP_TIME * self.__random.uniform(0.8, 1.2))

    monkeypatch.setattr(sd, 'InputStream', InputStream)


@pytest.fixture
def mock_time(monkeypatch):
    monkeypatch.setattr(times, 'time', time)
