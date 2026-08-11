import ctypes
import multiprocessing as mp
import sys
import typing as t
from multiprocessing import connection

from threa import Runnable

from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames

from .source_recorder import SourceControl, SourceFailure, SourceRecorder, SourceUpdate

STOP_TIMEOUT = 2.0
LINUX_PROCESS_NAME_LIMIT = 15
PR_SET_NAME = 15


class SourceProcess(Runnable):
    connection: connection.Connection
    process: mp.Process
    stop_event: t.Any

    def __init__(
        self,
        cfg: Cfg,
        tracks: t.Sequence[Track],
        track_names: DeviceTrackNames | None = None,
    ) -> None:
        self.cfg = cfg
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.tracks = tracks
        self.track_names = track_names or {}
        self.started: bool = False
        self.pending_updates: list[SourceUpdate | SourceFailure] = []

    @property
    def required_channels(self) -> int:
        return max(int(channel) for track in self.tracks for channel in track.channels)

    @property
    def is_alive(self) -> bool:
        return self.started and self.process.is_alive()

    @property
    def recorder_cfg(self) -> Cfg:
        cfg = self.cfg.with_device_profile(self.name)
        console = cfg.console.model_copy(update={'gui': False})
        return cfg.model_copy(update={'console': console})

    def start(self) -> None:
        assert not self.started
        self.connection, child = mp.Pipe()
        self.stop_event = mp.Event()
        process_name = _source_process_name(self.name)
        kwargs = {
            'cfg': self.recorder_cfg,
            'connection': child,
            'process_name': process_name,
            'stop_event': self.stop_event,
            'tracks': self.tracks,
            'track_names': self.track_names,
        }
        self.process = mp.Process(
            target=_run_source_recorder,
            kwargs=kwargs,
            name=process_name,
        )
        self.process.start()
        self.started = True
        self.stopped = False
        super().start()

    def stop(self) -> None:
        if not self.started:
            return
        self.running = False
        self.stop_event.set()

    def finish(self) -> None:
        self.stop()

    def set_track_names(self, track_names: DeviceTrackNames) -> None:
        self.track_names = track_names
        if self.started:
            self.connection.send(SourceControl(track_names=track_names))

    def set_cfg(self, cfg: Cfg) -> None:
        self.cfg = cfg
        if self.started:
            self.connection.send(SourceControl(cfg=self.recorder_cfg))

    def join(self, timeout: float | None = None) -> None:
        if not self.started:
            return
        self.process.join(STOP_TIMEOUT if timeout is None else timeout)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join()
        self.pending_updates = []
        while _connection_ready(self.connection):
            try:
                update = self.connection.recv()
            except (EOFError, OSError):
                break
            self.pending_updates.append(t.cast(SourceUpdate | SourceFailure, update))
        self.connection.close()
        self.running = False
        self.started = False
        self.stopped = True

    def take_updates(self) -> list[SourceUpdate | SourceFailure]:
        updates, self.pending_updates = self.pending_updates, []
        return updates


def _run_source_recorder(
    cfg: Cfg,
    connection: connection.Connection,
    stop_event: t.Any,
    tracks: t.Sequence[Track],
    track_names: DeviceTrackNames | None = None,
    process_name: str | None = None,
) -> None:
    _set_process_name(process_name)
    try:
        SourceRecorder(
            cfg=cfg,
            connection=connection,
            stop_event=stop_event,
            tracks=tracks,
            track_names=track_names,
        )
    except (OSError, RuntimeError, ValueError) as e:
        source_name = tracks[0].source.name
        connection.send(
            SourceFailure(message=f'{type(e).__name__}: {e}', source_name=source_name)
        )


def _connection_ready(conn: connection.Connection) -> bool:
    try:
        return conn.poll()
    except OSError:
        return False


def _source_process_name(source_name: str) -> str:
    source = ''.join(
        c if c.isascii() and c.isalnum() else '-' for c in source_name
    ).strip('-')
    return f'recs-src-{source or "source"}'


def _set_process_name(name: str | None) -> None:
    if name is None or not sys.platform.startswith('linux'):
        return

    encoded = name.encode()[:LINUX_PROCESS_NAME_LIMIT]
    try:
        ctypes.CDLL(None).prctl(PR_SET_NAME, ctypes.c_char_p(encoded), 0, 0, 0)
    except (AttributeError, OSError):
        return
