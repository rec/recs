import typing as t
from pathlib import Path
from test.conftest import DEVICES, DEVICES_FILE

import pytest

from recs.base import RecsError
from recs.base.cfg_raw import CfgRaw
from recs.cfg import Cfg
from recs.cfg.track import Track
from recs.ui import recorder
from recs.ui.recorder import Recorder


class FakePoller:
    def __init__(self, interval: float) -> None:
        self.snapshots: list[dict[str, t.Any] | None] = []

    def latest(self) -> dict[str, t.Any] | None:
        return self.snapshots.pop(0) if self.snapshots else None

    def poll(self) -> None:
        pass


class FakeConnection:
    def poll(self) -> bool:
        return False


class FakeSourceProcess:
    def __init__(self, cfg: CfgRaw, tracks: t.Sequence[Track]) -> None:
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.connection = FakeConnection()
        self.started = False
        self.running = False
        self.start_count = 0

    @property
    def is_alive(self) -> bool:
        return self.started and self.running

    @property
    def required_channels(self) -> int:
        return self.source.channels

    def join(self, timeout: float | None = None) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True
        self.running = True
        self.start_count += 1

    def stop(self) -> None:
        self.running = False


def test_recorder_fails(mock_devices):
    with pytest.raises(RecsError) as e:
        Recorder(Cfg(include=['e'], exclude=['e']))
    assert e.value.args == ('No channels selected',)


def test_recorder_replaces_returning_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    rec = Recorder(Cfg(devices=Path(DEVICES_FILE), silent=True))
    mic_info = next(info for info in DEVICES if info['name'] == 'Mic')
    mic = rec.hardware['Mic']

    rec.poller.snapshots = [
        {'Mic': mic_info, 'Unexpected': mic_info},
        {},
        {'Mic': mic_info},
    ]

    rec._poll_devices()
    assert mic.started
    assert mic.start_count == 1
    assert not any(
        source.started for name, source in rec.hardware.items() if name != 'Mic'
    )

    rec._poll_devices()
    rec._reap_sources()
    assert not mic.started

    rec._poll_devices()
    assert mic.started
    assert mic.start_count == 2
