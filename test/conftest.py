import copy
import json
import multiprocessing.dummy
from datetime import datetime, timedelta
from multiprocessing import connection
from pathlib import Path

import pytest

from recs.cfg import device
from recs.ui import device_process, device_recorder

DEVICES_FILE = Path(__file__).parent / 'devices.json'
DEVICES = json.loads(DEVICES_FILE.read_text())

BLOCK_SIZE = 0x80
SLEEP_TIME = 0.00001

TIME = datetime(2023, 10, 15, 16, 49, 21, 502)
TIMESTAMP = TIME.timestamp()
DELTA = timedelta(seconds=1)


def query_devices(kind=None):
    assert kind is None
    return copy.deepcopy(DEVICES)


def wait(connections, timeout=None):
    return [c for c in connections if c.poll(device_recorder.POLL_TIMEOUT)]


@pytest.fixture
def mock_mp(monkeypatch):
    monkeypatch.setattr(connection, 'wait', wait)
    monkeypatch.setattr(device_process, 'mp', multiprocessing.dummy)


@pytest.fixture
def mock_devices(monkeypatch):
    monkeypatch.setattr(device, 'query_devices', query_devices)


@pytest.fixture
def mock_input_streams(monkeypatch, mock_devices, mock_mp):
    import sounddevice as sd

    from .mock_input_stream import ThreadInputStream

    monkeypatch.setattr(sd, 'InputStream', ThreadInputStream)
