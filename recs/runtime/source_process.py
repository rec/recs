import ctypes
import multiprocessing as mp
import sys
import threading
from collections.abc import Sequence
from multiprocessing import connection
from pathlib import Path
from typing import Any, cast

from threa import Runnable

from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames
from recs.recording.session_record import MarkerPosition
from recs.runtime import source_messages, source_transport

from . import source_recorder

STOP_TIMEOUT = 2.0
LINUX_PROCESS_NAME_LIMIT = 15
PR_SET_NAME = 15


class SourceControlTransport:
    def __init__(self, connection: connection.Connection) -> None:
        self.connection = connection
        self.lock = threading.Lock()
        self.control = source_messages.SourceControl()
        self.available = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=self._send,
            daemon=True,
            name='SourceControls',
        )

    def start(self) -> None:
        self.thread.start()

    def publish(self, control: source_messages.SourceControl) -> None:
        with self.lock:
            self.control = source_messages.SourceControl(
                cfg=control.cfg if control.cfg is not None else self.control.cfg,
                cfg_revision=(
                    control.cfg_revision
                    if control.cfg_revision is not None
                    else self.control.cfg_revision
                ),
                session_directory=(
                    control.session_directory
                    if control.session_directory is not None
                    else self.control.session_directory
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
                waveforms_enabled=(
                    control.waveforms_enabled
                    if control.waveforms_enabled is not None
                    else self.control.waveforms_enabled
                ),
                writing_enabled=(
                    control.writing_enabled
                    if control.writing_enabled is not None
                    else self.control.writing_enabled
                ),
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
                control, self.control = self.control, source_messages.SourceControl()
            if control == source_messages.SourceControl():
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
        session_directory: Path,
        track_names: SourceTrackNames | None = None,
    ) -> None:
        self.cfg = cfg
        self.name = tracks[0].source.key
        self.source = tracks[0].source
        self.tracks = tracks
        self.session_directory = session_directory
        self.track_names = track_names or {}
        self.waveforms_enabled = False
        self.writing_enabled = True
        self.waveform_generation = 0
        self.started: bool = False
        self.pending_updates: list[
            source_messages.SourceUpdate | source_messages.SourceFailure
        ] = []
        self.expected_stop = False
        self.marker_position: MarkerPosition | None = None

    @property
    def required_channels(self) -> int:
        return max(int(channel) for track in self.tracks for channel in track.channels)

    @property
    def is_alive(self) -> bool:
        return self.started and self.process.is_alive()

    @property
    def recorder_cfg(self) -> Cfg:
        cfg = self.cfg.with_device_profile(self.source.name)
        console = cfg.console.model_copy(update={'gui': False})
        return cfg.model_copy(update={'console': console})

    def start(self) -> None:
        assert not self.started
        self.marker_position = None
        if self.waveforms_enabled:
            self.waveform_generation += 1
        self.connection, child_updates = mp.Pipe(duplex=False)
        child_controls, self.control_connection = mp.Pipe(duplex=False)
        self.stop_event = mp.Event()
        process_name = _source_process_name(self.source.name)
        kwargs = {
            'cfg': self.recorder_cfg,
            'control_connection': child_controls,
            'process_name': process_name,
            'session_directory': self.session_directory,
            'stop_event': self.stop_event,
            'tracks': self.tracks,
            'track_names': self.track_names,
            'update_connection': child_updates,
            'waveforms_enabled': self.waveforms_enabled,
            'writing_enabled': self.writing_enabled,
            'waveform_generation': self.waveform_generation,
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
        self.marker_position = None
        if not self.started:
            return
        self.running = False
        self.expected_stop = True
        self.stop_event.set()

    def finish(self) -> None:
        self.stop()

    def set_track_names(self, track_names: SourceTrackNames) -> None:
        self.track_names = track_names
        if self.started:
            self.control_transport.publish(
                source_messages.SourceControl(track_names=track_names)
            )

    def set_tracks(self, tracks: list[Track], track_names: SourceTrackNames) -> None:
        self.tracks = tracks
        self.track_names = track_names
        if self.started:
            self.control_transport.publish(
                source_messages.SourceControl(
                    track_names=track_names,
                    tracks=tracks,
                )
            )

    def set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        self.cfg = cfg
        if self.started:
            self.control_transport.publish(
                source_messages.SourceControl(
                    cfg=self.recorder_cfg, cfg_revision=revision
                )
            )

    def set_session_directory(self, session_directory: Path) -> None:
        self.session_directory = session_directory
        if self.started:
            self.control_transport.publish(
                source_messages.SourceControl(session_directory=session_directory)
            )

    def calibrate(self, tracks: list[str]) -> None:
        if self.started:
            self.control_transport.publish(
                source_messages.SourceControl(calibration_tracks=tracks)
            )

    def set_waveforms_enabled(self, enabled: bool) -> None:
        self.waveforms_enabled = enabled
        if self.started:
            self.control_transport.publish(
                source_messages.SourceControl(waveforms_enabled=enabled)
            )

    def set_writing_enabled(self, enabled: bool) -> None:
        self.writing_enabled = enabled
        if self.started:
            self.control_transport.publish(
                source_messages.SourceControl(writing_enabled=enabled)
            )

    def join(self, timeout: float | None = None) -> None:
        if not self.started:
            return
        finished = threading.Event()
        reader = threading.Thread(
            target=self._drain_updates, args=(finished,), name='SourceFinalUpdates'
        )
        reader.start()
        self.process.join(STOP_TIMEOUT if timeout is None else timeout)
        forced = False
        if self.process.is_alive():
            self.process.terminate()
            self.process.join()
            forced = True
        finished.set()
        reader.join()
        self._record_exit_failure(forced)
        self.control_transport.stop()
        self.control_connection.close()
        self.connection.close()
        self.running = False
        self.started = False
        self.stopped = True

    def _drain_updates(self, finished: threading.Event) -> None:
        while True:
            if not _connection_ready(self.connection):
                if finished.wait(0.01):
                    if not _connection_ready(self.connection):
                        return
                continue
            try:
                update = self.connection.recv()
            except (EOFError, OSError):
                break
            self.pending_updates.append(
                cast(
                    source_messages.SourceUpdate | source_messages.SourceFailure,
                    update,
                )
            )

    def _record_exit_failure(self, forced: bool) -> None:
        if any(
            isinstance(update, source_messages.SourceFailure)
            for update in self.pending_updates
        ):
            return
        exitcode = self.process.exitcode
        unexpected_exit = exitcode not in (0, None) and not self.expected_stop
        if not forced and not unexpected_exit:
            return
        final_update = next(
            (
                update
                for update in reversed(self.pending_updates)
                if isinstance(update, source_messages.SourceUpdate)
            ),
            None,
        )
        stop_kind = 'forced_termination' if forced else 'unexpected_exit'
        self.pending_updates.append(
            source_messages.SourceFailure(
                message=f'{self.name} source process {stop_kind}',
                source_name=self.name,
                exitcode=exitcode,
                final_frame_count=final_update.frame_count if final_update else None,
                last_callback_timestamp=final_update.timestamp
                if final_update
                else None,
                stop_kind=stop_kind,
            )
        )

    def take_updates(
        self,
    ) -> list[source_messages.SourceUpdate | source_messages.SourceFailure]:
        updates, self.pending_updates = self.pending_updates, []
        return updates


def _run_source_recorder(
    cfg: Cfg,
    control_connection: connection.Connection,
    session_directory: Path,
    stop_event: Any,
    tracks: Sequence[Track],
    update_connection: connection.Connection,
    track_names: SourceTrackNames | None = None,
    process_name: str | None = None,
    waveforms_enabled: bool = False,
    waveform_generation: int = 0,
    writing_enabled: bool = True,
) -> None:
    _set_process_name(process_name)
    transport = source_transport.SourceUpdateTransport(update_connection)
    transport.start()
    try:
        recorder = source_recorder.SourceRecorder(
            cfg=cfg,
            control_connection=control_connection,
            session_directory=session_directory,
            stop_event=stop_event,
            tracks=tracks,
            track_names=track_names,
            update_transport=transport,
            waveforms_enabled=waveforms_enabled,
            waveform_generation=waveform_generation,
            writing_enabled=writing_enabled,
        )
        recorder.run()
    except Exception as e:
        source_name = tracks[0].source.key
        transport.publish(_source_failure(e, source_name))
    finally:
        transport.finish()
        update_connection.close()


def _connection_ready(conn: connection.Connection) -> bool:
    try:
        return conn.poll()
    except OSError:
        return False


def _source_failure(
    error: Exception, source_name: str
) -> source_messages.SourceFailure:
    import sounddevice

    message = f'{type(error).__name__}: {error}'
    if not isinstance(error, sounddevice.PortAudioError):
        return source_messages.SourceFailure(
            message=message,
            source_name=source_name,
            exception_type=type(error).__name__,
            stop_kind='crash',
        )

    portaudio_code = error.args[1] if len(error.args) >= 2 else None
    host_api = None
    host_error_code = None
    host_error_message = None
    if len(error.args) >= 3:
        host_index, host_error_code, host_error_message = error.args[2]
        try:
            host_api = str(sounddevice.query_hostapis(host_index)['name'])
        except (IndexError, KeyError, sounddevice.PortAudioError):
            pass
    unavailable = portaudio_code == -9985 or any(
        phrase in str(error).lower()
        for phrase in ('device unavailable', 'device or resource busy', 'in use')
    )
    if unavailable:
        message += (
            '. The audio device may already be in use by another Recs instance '
            'or application'
        )
    return source_messages.SourceFailure(
        message=message,
        source_name=source_name,
        exception_type=type(error).__name__,
        stop_kind='crash',
        portaudio_code=portaudio_code,
        host_api=host_api,
        host_error_code=host_error_code,
        host_error_message=host_error_message,
        device_unavailable=unavailable,
    )


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
