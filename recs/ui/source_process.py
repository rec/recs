import ctypes
import multiprocessing as mp
import sys
import threading
from collections.abc import Sequence
from multiprocessing import connection
from typing import Any, cast

from threa import Runnable

from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames

from . import source_recorder

STOP_TIMEOUT = 2.0
LINUX_PROCESS_NAME_LIMIT = 15
PR_SET_NAME = 15


class SourceControlTransport:
    def __init__(self, connection: connection.Connection) -> None:
        self.connection = connection
        self.lock = threading.Lock()
        self.control = source_recorder.SourceControl()
        self.available = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=self._send,
            daemon=True,
            name='SourceControls',
        )

    def start(self) -> None:
        self.thread.start()

    def publish(self, control: source_recorder.SourceControl) -> None:
        with self.lock:
            self.control = source_recorder.SourceControl(
                cfg=control.cfg if control.cfg is not None else self.control.cfg,
                cfg_revision=(
                    control.cfg_revision
                    if control.cfg_revision is not None
                    else self.control.cfg_revision
                ),
                track_names=(
                    control.track_names
                    if control.track_names is not None
                    else self.control.track_names
                ),
                calibration_tracks=(
                    control.calibration_tracks
                    if control.calibration_tracks is not None
                    else self.control.calibration_tracks
                ),
                tracks=control.tracks
                if control.tracks is not None
                else self.control.tracks,
            )
            self.available.set()

    def stop(self) -> None:
        self.stopped.set()
        self.available.set()

    def _send(self) -> None:
        while not self.stopped.is_set():
            self.available.wait()
            self.available.clear()
            with self.lock:
                control, self.control = self.control, source_recorder.SourceControl()
            if control == source_recorder.SourceControl():
                continue
            try:
                self.connection.send(control)
            except (BrokenPipeError, EOFError, OSError):
                return


class SourceProcess(Runnable):
    connection: connection.Connection
    control_connection: connection.Connection
    control_transport: SourceControlTransport
    process: mp.Process
    stop_event: Any

    def __init__(
        self,
        cfg: Cfg,
        tracks: Sequence[Track],
        track_names: DeviceTrackNames | None = None,
    ) -> None:
        self.cfg = cfg
        self.name = tracks[0].source.name
        self.source = tracks[0].source
        self.tracks = tracks
        self.track_names = track_names or {}
        self.started: bool = False
        self.pending_updates: list[
            source_recorder.SourceUpdate | source_recorder.SourceFailure
        ] = []

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
        self.connection, child_updates = mp.Pipe(duplex=False)
        child_controls, self.control_connection = mp.Pipe(duplex=False)
        self.stop_event = mp.Event()
        process_name = _source_process_name(self.name)
        kwargs = {
            'cfg': self.recorder_cfg,
            'control_connection': child_controls,
            'process_name': process_name,
            'stop_event': self.stop_event,
            'tracks': self.tracks,
            'track_names': self.track_names,
            'update_connection': child_updates,
        }
        self.process = mp.Process(
            target=_run_source_recorder,
            kwargs=kwargs,
            name=process_name,
        )
        self.process.start()
        self.control_transport = SourceControlTransport(self.control_connection)
        self.control_transport.start()
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
            self.control_transport.publish(
                source_recorder.SourceControl(track_names=track_names)
            )

    def set_tracks(self, tracks: list[Track], track_names: DeviceTrackNames) -> None:
        self.tracks = tracks
        self.track_names = track_names
        if self.started:
            self.control_transport.publish(
                source_recorder.SourceControl(
                    track_names=track_names,
                    tracks=tracks,
                )
            )

    def set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        self.cfg = cfg
        if self.started:
            self.control_transport.publish(
                source_recorder.SourceControl(
                    cfg=self.recorder_cfg, cfg_revision=revision
                )
            )

    def calibrate(self, tracks: list[str]) -> None:
        if self.started:
            self.control_transport.publish(
                source_recorder.SourceControl(calibration_tracks=tracks)
            )

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
            self.pending_updates.append(
                cast(
                    source_recorder.SourceUpdate | source_recorder.SourceFailure,
                    update,
                )
            )
        self.control_transport.stop()
        self.control_connection.close()
        self.connection.close()
        self.running = False
        self.started = False
        self.stopped = True

    def take_updates(
        self,
    ) -> list[source_recorder.SourceUpdate | source_recorder.SourceFailure]:
        updates, self.pending_updates = self.pending_updates, []
        return updates


def _run_source_recorder(
    cfg: Cfg,
    control_connection: connection.Connection,
    stop_event: Any,
    tracks: Sequence[Track],
    update_connection: connection.Connection,
    track_names: DeviceTrackNames | None = None,
    process_name: str | None = None,
) -> None:
    _set_process_name(process_name)
    transport = source_recorder.SourceUpdateTransport(update_connection)
    transport.start()
    try:
        source_recorder.SourceRecorder(
            cfg=cfg,
            control_connection=control_connection,
            stop_event=stop_event,
            tracks=tracks,
            track_names=track_names,
            update_transport=transport,
        )
    except (OSError, RuntimeError, ValueError) as e:
        source_name = tracks[0].source.name
        transport.publish(
            source_recorder.SourceFailure(
                message=f'{type(e).__name__}: {e}', source_name=source_name
            )
        )
    finally:
        transport.finish()


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
