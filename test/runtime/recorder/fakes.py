import json
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from threa import Runnable

from recs.base.errors import RecsError
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.daemon import gui_protocol
from recs.recording.session_record import MarkerPosition
from recs.runtime.recorder import Recorder
from recs.runtime.source_messages import SourceUpdate
from recs.ui.key_events import KeyEvent


class DiskUsage(NamedTuple):
    total: int
    used: int
    free: int


class FakePoller(Runnable):
    def __init__(self, interval: float) -> None:
        self.snapshots: list[dict[str, Any] | None] = []

    def latest(self) -> dict[str, Any] | None:
        return self.snapshots.pop(0) if self.snapshots else None

    def poll(self) -> None:
        pass


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    # These tests inspect operational events; native clock evidence has separate tests.
    return [
        r
        for e in path.read_text().splitlines()
        if (r := json.loads(e))['type'] != 'clock_observation'
    ]


def record_path(rec: Recorder) -> Path:
    return rec.session_directory / 'session-record.jsonl'


class FakeConnection:
    def __init__(self) -> None:
        self.messages: list[SourceUpdate] = []

    def poll(self) -> bool:
        return bool(self.messages)

    def recv(self) -> SourceUpdate:
        return self.messages.pop(0)


class FakeSourceProcess:
    def __init__(
        self,
        cfg: Cfg,
        tracks: Sequence[Track],
        session_directory: Path,
        track_names: dict[str, dict[str, int]] | None = None,
    ) -> None:
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.tracks = tracks
        self.connection = FakeConnection()
        self.started = False
        self.running = False
        self.alive = False
        self.start_count = 0
        self.stop_count = 0
        self.join_count = 0
        self.track_names = track_names or {}
        self.cfg = cfg
        self.session_directory = session_directory
        self.pending_updates: list[SourceUpdate] = []
        self.waveforms_enabled = False
        self.writing_enabled = True
        self.marker_position: MarkerPosition | None = None

    @property
    def is_alive(self) -> bool:
        return self.started and self.alive

    @property
    def required_channels(self) -> int:
        return self.source.channels

    def join(self, timeout: float | None = None) -> None:
        self.join_count += 1
        self.alive = False
        self.started = False

    def start(self) -> None:
        self.marker_position = None
        self.started = True
        self.running = True
        self.alive = True
        self.start_count += 1

    def stop(self) -> None:
        self.marker_position = None
        self.stop_count += 1
        self.running = False
        self.alive = False

    def set_track_names(self, track_names: dict[str, dict[str, int]]) -> None:
        self.track_names = track_names

    def set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        self.cfg = cfg
        self.cfg_revision = revision

    def set_session_directory(self, session_directory: Path) -> None:
        self.session_directory = session_directory

    def set_waveforms_enabled(self, enabled: bool) -> None:
        self.waveforms_enabled = enabled

    def set_writing_enabled(self, enabled: bool) -> None:
        self.writing_enabled = enabled

    def calibrate(self, tracks: list[str]) -> None:
        self.connection.messages.append(
            SourceUpdate(
                channels={},
                files=[],
                frames=0,
                source_name=self.name,
                calibration=dict.fromkeys(tracks, 6.0),
            )
        )

    def set_tracks(
        self, tracks: list[Track], track_names: dict[str, dict[str, int]]
    ) -> None:
        self.tracks = tracks
        self.track_names = track_names

    def take_updates(self) -> list[SourceUpdate]:
        updates, self.pending_updates = self.pending_updates, []
        return updates


class ClosedDisplay(Runnable):
    enabled = True
    closed = True

    def __init__(
        self,
        rows: Callable[[], Iterator[Mapping[str, object]]],
        cfg: Cfg,
        *,
        errors: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self.rows = rows
        self.cfg = cfg
        self.errors = errors or tuple
        super().__init__()

    def update(self) -> None:
        pass

    def take_key_events(self) -> list[KeyEvent]:
        return []


class FakeKeyRecorder:
    def __init__(self, events: list[KeyEvent]) -> None:
        self.events = events

    def take_events(self) -> list[KeyEvent]:
        events, self.events = self.events, []
        return events

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class FakeControlDisplay:
    closed = False

    def __init__(self, requests: list['FakeControlRequest']) -> None:
        self.requests = requests

    def take_key_events(self) -> list[KeyEvent]:
        return []

    def take_control_requests(self) -> list['FakeControlRequest']:
        requests, self.requests = self.requests, []
        return requests


class FakeControlRequest:
    def __init__(self, request: gui_protocol.Request | None = None) -> None:
        self.request = request or gui_protocol.Calibrate(type='calibrate')
        self.responses: list[gui_protocol.Response] = []

    def respond(self, response: gui_protocol.Response) -> None:
        self.responses.append(response)


def _raise_recs_error(message: str) -> None:
    raise RecsError(message)
