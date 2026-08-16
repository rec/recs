from collections.abc import Sequence
from typing import Any

import pytest

from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.ui import recorder
from recs.ui.recorder import Recorder
from recs.ui.source_recorder import SourceUpdate


class FakePoller:
    def __init__(self, interval: float) -> None:
        pass

    def latest(self) -> None:
        return None

    def poll(self) -> None:
        pass


class FakeSourceProcess:
    def __init__(
        self,
        cfg: Cfg,
        tracks: Sequence[Track],
        track_names: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.tracks = tracks
        self.connection = object()
        self.started = False
        self.running = False
        self.alive = False
        self.start_count = 0
        self.track_names = track_names or {}
        self.cfg = cfg
        self.pending_updates: list[SourceUpdate] = []

    @property
    def is_alive(self) -> bool:
        return False

    @property
    def required_channels(self) -> int:
        return max(self.source.channels, *(max(t.channels) for t in self.tracks))

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.running = False

    def join(self, timeout: float | None = None) -> None:
        pass

    def take_updates(self) -> list[Any]:
        return []


def _recorder(
    monkeypatch: pytest.MonkeyPatch,
    cfg: Cfg,
) -> Recorder:
    monkeypatch.setattr(recorder, 'DevicePoller', FakePoller)
    monkeypatch.setattr(recorder, 'SourceProcess', FakeSourceProcess)
    return Recorder(cfg)


def test_recorder_explains_dry_run_without_files(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    rec = _recorder(monkeypatch, Cfg(dry_run=True, include=['Mic'], silent=True))

    assert rec._no_file_explanation() == 'dry-run mode does not write files'


def test_recorder_explains_missing_audio_updates(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    rec = _recorder(monkeypatch, Cfg(include=['Mic'], silent=True))

    assert rec._no_file_explanation() == 'no audio updates were received'


def test_recorder_explains_quiet_or_short_audio(
    monkeypatch: pytest.MonkeyPatch,
    mock_devices: None,
) -> None:
    rec = _recorder(monkeypatch, Cfg(include=['Mic'], silent=True))
    rec.devices.frames['Mic'] = 48_000

    assert rec._no_file_explanation() == (
        'audio stayed below the noise floor or candidate files were shorter '
        'than shortest_file_time'
    )
