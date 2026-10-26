from collections.abc import Sequence
from pathlib import Path

import pytest
from dvice.health import DiscoveryStatus

from recs.base.state import ChannelState
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.track import Track
from recs.runtime import device_lifecycle
from recs.runtime.device_lifecycle import DeviceLifecycle
from recs.runtime.full_state import FullState
from recs.runtime.source_messages import BufferStats, SourceUpdate


class DrainingConnection:
    def __init__(self, messages: list[SourceUpdate]) -> None:
        self.messages = messages

    def poll(self) -> bool:
        return bool(self.messages)

    def recv(self) -> SourceUpdate:
        return self.messages.pop(0)


class ReapedSource:
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
        self.session_directory = session_directory
        self.started = True
        self.running = False
        self.connection = DrainingConnection(
            [
                SourceUpdate(
                    channels={'1': ChannelState()},
                    files=[],
                    frames=1,
                    source_name=self.name,
                ),
                SourceUpdate(
                    channels={'1': ChannelState()},
                    files=[],
                    frames=2,
                    source_name=self.name,
                ),
            ]
        )

    @property
    def is_alive(self) -> bool:
        return False

    def join(self, timeout: float | None = None) -> None:
        self.started = False

    def take_updates(self) -> list[SourceUpdate]:
        return []


class FakePoller:
    def poll(self) -> None:
        pass

    status = DiscoveryStatus()


def test_reap_drains_all_pending_source_messages() -> None:
    source = InputDevice(
        {
            'default_samplerate': 48_000,
            'max_input_channels': 1,
            'name': 'Mic',
        }
    )
    tracks = [Track(source, '1')]
    state = FullState([(source, tracks)], Cfg().aliases)
    updates: list[SourceUpdate] = []
    lifecycle = DeviceLifecycle(
        Cfg(),
        state,
        Path('session'),
        saved_tracks={},
        track_names={},
        initial_tracks=[(source, tracks)],
        warning=lambda message: None,
        event=lambda *args, **kwargs: None,
        file_update=lambda update, source: updates.append(update),
        calibration_update=lambda source, values: None,
        buffer_update=lambda source, stats: None,
        write_error=lambda source, error: None,
        source_process=ReapedSource,
        device_poller=lambda interval: FakePoller(),
    )

    lifecycle.reap()

    assert [update.frames for update in updates] == [1, 2]


def test_diagnostics_are_periodic_with_immediate_loss_and_final_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(device_lifecycle, 'monotonic', lambda: clock[0])
    reports: list[BufferStats] = []
    source = InputDevice(
        {'name': 'Mic', 'max_input_channels': 1, 'default_samplerate': 48_000}
    )
    tracks = [Track(source, '1')]
    lifecycle = DeviceLifecycle(
        Cfg(),
        FullState([(source, tracks)], Cfg().aliases),
        Path('session'),
        saved_tracks={},
        track_names={},
        initial_tracks=[(source, tracks)],
        warning=lambda message: None,
        event=lambda *args, **kwargs: None,
        file_update=lambda *args: None,
        calibration_update=lambda *args: None,
        buffer_update=lambda source, stats: reports.append(stats),
        write_error=lambda *args: None,
        source_process=ReapedSource,
        device_poller=lambda interval: FakePoller(),
    )
    for tick in range(12):
        clock[0] = tick
        lifecycle.receive_message(
            SourceUpdate(
                {},
                [],
                0,
                'Mic',
                buffer_stats=BufferStats(dropped_frames=1 if tick >= 2 else 0),
                capture_complete=tick == 11,
            )
        )
    assert len(reports) == 4  # Initial, first loss, five seconds later, final.
    assert [r.dropped_frames for r in reports] == [0, 1, 1, 1]
