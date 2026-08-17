from collections.abc import Sequence
from pathlib import Path

from recs.base.state import ChannelState
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.track import Track
from recs.ui.device_lifecycle import DeviceLifecycle
from recs.ui.full_state import FullState
from recs.ui.source_recorder import SourceUpdate


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

    def latest(self) -> None:
        return None


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
        source_process=ReapedSource,
        device_poller=lambda interval: FakePoller(),
    )

    lifecycle.reap()

    assert [update.frames for update in updates] == [1, 2]
