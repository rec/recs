import json
import os
import sys
import uuid
from collections.abc import Iterator, Sequence
from multiprocessing import connection
from pathlib import Path
from typing import cast

from reccy import logging
from threa import HasThread, Runnable, Runnables

from recs.base import times
from recs.base.errors import ErrorRecord
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.cfg.file_source import FileSource
from recs.cfg.source import Source
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames
from recs.daemon import external_ipc, gui_ipc

from . import (
    calibration,
    device_lifecycle,
    disk_control,
    disk_monitor,
    gui_process,
    live,
    recording_control,
    recording_paths,
    recording_session,
    session_manifest,
)
from .device_poller import DevicePoller
from .full_state import FullState
from .key_events import KeyEvent, make_key_recorder
from .source_process import SourceProcess
from .source_recorder import POLL_TIMEOUT, BufferStats, SourceFailure, SourceUpdate

LOGGER = logging.get_logger(__name__)
SOURCE_STALL_TIMEOUT = device_lifecycle.SOURCE_STALL_TIMEOUT


class Recorder(Runnables):
    def __init__(
        self,
        cfg: Cfg,
        saved_settings: settings.LoadedSettings | None = None,
        *,
        display: bool = True,
    ) -> None:
        super().__init__()

        saved_settings = saved_settings or settings.LoadedSettings(cfg=cfg)
        self.saved_tracks = {
            name: list(tracks) for name, tracks in saved_settings.tracks.items()
        }
        all_tracks = device_lifecycle.DeviceLifecycle.initial_tracks(
            cfg, self.saved_tracks
        )
        self.warnings: list[ErrorRecord] = []
        track_names = saved_settings.track_names
        self.state = FullState(all_tracks, cfg.aliases)
        self.session_start_time = self.state.start_time
        self.daemon_record_directory = (
            recording_paths.daemon_record_directory(cfg)
            if not cfg.directory.output_directory
            else None
        )
        self.cfg = recording_paths.with_default_output_directory(
            cfg, self.state.start_time
        )
        self.external = (
            external_ipc.ExternalServer() if gui_ipc.daemon_mode_enabled() else None
        )
        if gui_ipc.daemon_mode_enabled():
            display_type = gui_ipc.DaemonGuiServer
        elif self.cfg.console.gui:
            display_type = gui_process.GuiProcess
        else:
            display_type = live.Live
        self.live = (
            display_type(
                self.rows,
                self.cfg,
                errors=self.error_records
                if gui_ipc.daemon_mode_enabled()
                else self.error_messages,
            )
            if display
            else None
        )
        self.session = recording_session.RecordingSession(
            str(uuid.uuid4()), self.session_start_time
        )
        self.key_recorder = make_key_recorder(cfg)
        self.disk_monitor = disk_monitor.DiskMonitor(self.cfg)
        self.devices = device_lifecycle.DeviceLifecycle(
            self.cfg,
            self.state,
            self.saved_tracks,
            track_names,
            all_tracks,
            self._record_warning,
            self._record_event,
            self._record_device_file_update,
            self._record_calibration_result,
            self._record_device_buffer_update,
            SourceProcess,
            DevicePoller,
        )
        self.control = recording_control.RecordingControl(
            self.cfg,
            self.saved_tracks,
            track_names,
            self.state,
            self.session,
            self.devices,
            self.disk_monitor,
            lambda record: self._write_manifest_record(record),
            self._replace_cfg,
            lambda: list(self.rows()),
            self.error_records,
            self._manifest_path,
            self._receive_pending_updates,
            self._finish_manifest,
            self._start_recording_session,
        )
        self.calibration = calibration.Calibration(
            self.cfg,
            self.devices.hardware,
            self.control.track_for_channel,
            self._receive_connection,
            self._record_event,
            self.control.set_cfg_value,
        )
        self.control.calibrate = self.calibration.calibrate
        self.disk_control = disk_control.DiskControl(
            self.cfg,
            self.session,
            self.devices,
            self.disk_monitor,
            self.control,
            lambda record: self._write_manifest_record(record),
            self._record_warning,
            self._replace_cfg,
            self._receive_pending_updates,
            self._start_manifest,
            self._finish_manifest,
            self._manifest_path,
            lambda: self.session_start_time,
        )
        if isinstance(self.live, gui_ipc.DaemonGuiServer):
            self.live.external_rows = self._publish_external_rows

        runnables = tuple(self.devices.files.values()) + (self.key_recorder,)
        if self.devices.poller is not None:
            runnables += (self.devices.poller,)
        if self.live and self.live.enabled:
            ui_time = 1 / self.cfg.console.ui_refresh_rate
            live_thread = HasThread(
                self.live.update,
                looping=True,
                name='LiveUpdate',
                pre_delay=ui_time,
            )
            runnables += live_thread, self.live

        self.runnables = runnables
        self._record_startup_input_errors(all_tracks)

    @property
    def sources(self) -> dict[str, SourceProcess]:
        return self.devices.sources

    @property
    def recording_paused(self) -> bool:
        return self.control.recording_paused

    @recording_paused.setter
    def recording_paused(self, value: bool) -> None:
        self.control.recording_paused = value

    @property
    def recording_stopped(self) -> bool:
        return self.control.recording_stopped

    @recording_stopped.setter
    def recording_stopped(self, value: bool) -> None:
        self.control.recording_stopped = value

    @property
    def session_stopped(self) -> bool:
        return self.control.session_stopped

    @session_stopped.setter
    def session_stopped(self, value: bool) -> None:
        self.control.session_stopped = value

    @property
    def track_names(self) -> DeviceTrackNames:
        return self.control.track_names

    @track_names.setter
    def track_names(self, value: DeviceTrackNames) -> None:
        self.control.track_names = value

    @property
    def hardware(self) -> dict[str, SourceProcess]:
        return self.devices.hardware

    @property
    def files(self) -> dict[str, SourceProcess]:
        return self.devices.files

    @property
    def frames(self) -> dict[str, int]:
        return self.devices.frames

    @property
    def buffer_stats(self) -> dict[str, BufferStats]:
        return self.devices.buffer_stats

    @property
    def buffer_drops_reported(self) -> dict[str, int]:
        return self.devices.buffer_drops_reported

    @property
    def source_frames_at_start(self) -> dict[str, int]:
        return self.devices.source_frames_at_start

    @property
    def source_start_times(self) -> dict[str, float]:
        return self.devices.source_start_times

    @property
    def source_last_updates(self) -> dict[str, float]:
        return self.devices.source_last_updates

    @property
    def lag_reported(self) -> set[str]:
        return self.devices.lag_reported

    @property
    def poller(self) -> DevicePoller | None:
        return self.devices.poller

    @property
    def failed(self) -> set[str]:
        return self.devices.failed

    @property
    def present(self) -> set[str]:
        return self.devices.present

    @present.setter
    def present(self, value: set[str]) -> None:
        self.devices.present = value

    @property
    def no_devices_reported(self) -> bool:
        return self.devices.no_devices_reported

    @no_devices_reported.setter
    def no_devices_reported(self, value: bool) -> None:
        self.devices.no_devices_reported = value

    @property
    def no_channels_reported(self) -> bool:
        return self.devices.no_channels_reported

    @no_channels_reported.setter
    def no_channels_reported(self, value: bool) -> None:
        self.devices.no_channels_reported = value

    def _record_device_file_update(
        self, update: SourceUpdate, source: SourceProcess
    ) -> None:
        self.session.record_files(
            update.files,
            update.file_end_frames or {},
            update.file_end_timestamps or {},
        )
        for file_record in update.file_records or []:
            self.session.record_file_started(
                file_record,
                file_record.source_name
                if isinstance(source.source, FileSource)
                else None,
            )
        if update.track_layout is not None:
            self.state.replace_source(source.source, source.tracks, self.cfg.aliases)
            self.state.set_track_names(self.track_names)

    def _record_calibration_result(self, source: str, values: dict[str, float]) -> None:
        self.calibration.results[source] = values

    def _record_device_buffer_update(self, source: str, stats: BufferStats) -> None:
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                type='buffer_overflow',
                timestamp=session_manifest.timestamp_to_json(stats.last_drop_timestamp),
                source=source,
                dropped_blocks=stats.dropped_blocks,
                dropped_frames=stats.dropped_frames,
                max_queued_seconds=stats.max_queued_seconds,
                queued_seconds=stats.queued_seconds,
            )
        )

    def start(self) -> None:
        if self.external is not None:
            try:
                self.external.start()
            except OSError as e:
                self.external.close()
                self.external = None
                self._record_warning(f'Cannot start external IPC server: {e}')
                if isinstance(self.live, gui_ipc.DaemonGuiServer):
                    self.live.external_ipc_error = str(e)
        super().start()
        Runnable.start(self)

    def rows(self) -> Iterator[dict[str, object]]:
        for row in self.state.rows():
            if device := row.get('device'):
                for source, name in self.state.source_names.items():
                    if name == device and (stats := self.buffer_stats.get(source)):
                        row |= {
                            'buffer': stats.queued_seconds,
                            'dropped': stats.dropped_frames,
                        }
            yield row

    def error_messages(self) -> list[str]:
        return [warning.message for warning in self.warnings]

    def error_records(self) -> list[ErrorRecord]:
        return self.warnings.copy()

    def _record_startup_input_errors(
        self,
        all_tracks: Sequence[tuple[Source, Sequence[Track]]],
    ) -> None:
        if self.files:
            return
        if not self.cfg.input_devices:
            self._report_no_devices()
        elif not all_tracks:
            self._report_no_channels()

    def run(self) -> None:
        with raise_keyboard_interrupt_on_signal():
            try:
                self._start_manifest()
                self._run()
            except KeyboardInterrupt:
                print('Interrupted', file=sys.stderr)
            finally:
                if self.external is not None:
                    self.external.close()
                self._receive_pending_updates()
                self._finish_manifest()
                if self.cfg.general.silence_preview:
                    print(json.dumps(self._silence_preview_report(), indent=2))
                elif self.cfg.general.calibrate or self.cfg.general.verbose:
                    print(json.dumps(self.state.db_ranges(), indent=2))
        self._summary()
        if self.cfg.console.open_output_folder:
            recording_paths.open_folder(self._output_folder())

    def _summary(self) -> None:
        print(f'Recording time: {_summary_time(self.state.elapsed_time)}')
        files = sorted(path for path in self.session.files_written if path.exists())
        if files:
            print('Files written:')
            for path in files:
                print(f'  {path}')
        else:
            print('Files written: none')
            print(f'No files written because {self._no_file_explanation()}.')

    def _no_file_explanation(self) -> str:
        if self.cfg.general.dry_run:
            return 'dry-run mode does not write files'
        if self.cfg.general.calibrate:
            return 'calibration mode does not write files'
        if self.cfg.general.silence_preview:
            return 'silence preview mode does not write files'
        if self.failed:
            return f'sources failed: {", ".join(sorted(self.failed))}'
        if self.session.files_written:
            return 'all candidate files were removed or are no longer present'
        if not any(self.frames.values()):
            return 'no audio updates were received'
        return (
            'audio stayed below the noise floor or candidate files were shorter '
            'than shortest_file_time'
        )

    def _run(self) -> None:
        if self.cfg.console.gui:
            self._poll_devices()
        with self:
            try:
                while self.running:
                    if self._display_closed():
                        break
                    self._monitor_disk_space()
                    self._receive_key_events()
                    self._receive_control_requests()
                    self._poll_devices()
                    self._reap_sources()
                    self._stop_stalled_sources()
                    sources = [
                        source for source in self.sources.values() if source.is_alive
                    ]
                    self.state.set_online(
                        source.name for source in sources if source.running
                    )
                    if self._done(sources):
                        break

                    connections = [source.connection for source in sources]
                    if not connections:
                        times.sleep(POLL_TIMEOUT)
                        continue
                    for c in connection.wait(connections, timeout=POLL_TIMEOUT):
                        self._receive_connection(cast(connection.Connection, c))
            finally:
                for source in self.hardware.values():
                    source.stop()
                for source in self.hardware.values():
                    source.join()

    def _done(self, sources: Sequence[SourceProcess]) -> bool:
        if self.files and not self.hardware:
            return not sources
        return self._invocation_expired() and not any(
            source.running for source in sources
        )

    def _invocation_expired(self) -> bool:
        total = self.cfg.recording.total_run_time
        return bool(total and self.state.elapsed_time >= total)

    def _display_closed(self) -> bool:
        return bool(self.live and self.live.closed)

    def _monitor_disk_space(self) -> None:
        self.disk_control.monitor_disk_space()

    def _poll_devices(self) -> None:
        self.devices.poll(
            self.recording_paused,
            self.recording_stopped,
            self._invocation_expired(),
        )

    def _report_no_devices(self) -> None:
        if self.no_devices_reported:
            return
        warning = 'No input devices detected'
        self._record_warning(warning)
        self.no_devices_reported = True

    def _report_no_channels(self) -> None:
        if self.no_channels_reported:
            return
        warning = 'No channels selected'
        self._record_warning(warning)
        self.no_channels_reported = True

    def _reap_sources(self) -> None:
        self.devices.reap()

    def _stop_stalled_sources(self) -> None:
        self.devices.stop_stalled()

    def _receive_pending_updates(self) -> None:
        self._receive_key_events()
        self.devices.receive_pending_updates()

    def _receive_key_events(self) -> None:
        for event in self.key_recorder.take_events():
            self._record_key_event(event)
        if self.live is None:
            return
        for event in self.live.take_key_events():
            self._record_key_event(event)

    def _receive_control_requests(self) -> None:
        self.control.receive(
            cast(recording_control.ControlDisplay | None, self.live),
            self.external,
            self._record_warning,
            self.stop,
        )

    def _publish_external_rows(
        self,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        self.control.publish(self.external, rows, errors)

    def _receive_connection(self, conn: connection.Connection) -> bool:
        return self.devices.receive_connection(conn)

    def _receive_source_message(self, message: SourceUpdate | SourceFailure) -> None:
        self.devices.receive_message(message)

    def _receive_update(self, update: SourceUpdate) -> None:
        self.devices.receive_message(update)

    def _record_event(
        self,
        event_type: str,
        *,
        source: str,
        track: str | None = None,
        frame_count: int | None = None,
        start_frame: int | None = None,
        timestamp: float | None = None,
        value: object | None = None,
    ) -> None:
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(
                    recording_paths.timestamp_or_now(timestamp)
                ),
                type=event_type,
                source=source,
                track=track,
                frame_count=frame_count,
                start_frame=start_frame,
                value=value,
            )
        )

    def _record_key_event(self, event: KeyEvent) -> None:
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type=event.type,
                key=event.key,
                label=self.cfg.keys.labels.get(event.key),
            )
        )

    def _start_manifest(self) -> None:
        self.session.start(
            self._manifest_path(),
            dry_run=self.cfg.general.dry_run,
            silence_preview=self.cfg.general.silence_preview,
        )

    def _finish_manifest(self) -> None:
        self.session.finish(times.timestamp())

    def _start_recording_session(self) -> None:
        self.session_start_time = times.timestamp()
        self.session.reset(self.session_start_time)
        if self.daemon_record_directory is not None:
            output_directory = recording_paths.available_directory(
                self.daemon_record_directory
                / recording_paths.daemon_session_directory_name(self.session_start_time)
            )
            directory = self.cfg.directory.model_copy(
                update={'output_directory': str(output_directory)}
            )
            self.cfg = self.cfg.model_copy(update={'directory': directory})
            self.cfg.__dict__.pop('output_path_pattern', None)
            for source in self.sources.values():
                source.cfg = self.cfg
        self.control.cfg = self.cfg
        self.disk_monitor.cfg = self.cfg
        self.disk_control.cfg = self.cfg
        self.calibration.cfg = self.cfg
        self._start_manifest()
        self.session_stopped = False

    def _replace_cfg(self, cfg: Cfg) -> None:
        self.cfg = cfg
        self.devices.cfg = cfg
        self.disk_monitor.cfg = cfg
        self.disk_control.cfg = cfg
        self.calibration.cfg = cfg

    def _record_warning(self, warning: str) -> None:
        timestamp = session_manifest.timestamp_to_json(times.timestamp())
        LOGGER.error('%s', warning)
        self.warnings.append(ErrorRecord(timestamp=timestamp, message=warning))
        self._write_manifest_record(
            session_manifest.ManifestWarning(
                timestamp=timestamp,
                message=warning,
            )
        )

    def _write_manifest_record(
        self,
        record: session_manifest.ManifestEvent
        | session_manifest.ManifestFile
        | session_manifest.ManifestFooter
        | session_manifest.ManifestWarning,
    ) -> None:
        self.session.write(record)

    def _silence_preview_report(self) -> dict[str, object]:
        measurements = self.state.db_ranges()
        profiles = {}
        for source_name, source_state in self.state.state.items():
            source_measurements = [state.db_range for state in source_state.values()]
            noise_floor = max(source_measurements, default=0.0)
            profiles[source_name] = {
                'noise_floor': round(
                    noise_floor + self.cfg.recording.preview_headroom, 1
                )
            }
        return {
            'measurements': measurements,
            'profiles': profiles,
        }

    def _manifest_path(self) -> Path:
        paths = sorted(path for path in self.session.files_written if path.exists())
        if paths:
            parent = Path(os.path.commonpath([path.parent for path in paths]))
            return parent / 'recs-session.jsonl'

        output_directory = self.cfg.directory.output_directory
        if output_directory:
            return recording_paths.manifest_directory(
                output_directory, self.session_start_time
            ) / ('recs-session.jsonl')
        return Path('recs-session.jsonl')

    def _output_folder(self) -> Path:
        paths = sorted(path for path in self.session.files_written if path.exists())
        if paths:
            return Path(os.path.commonpath([path.parent for path in paths]))
        return recording_paths.existing_parent(self._manifest_path()).resolve()


def _summary_time(seconds: float) -> str:
    value = times.to_str(seconds)
    if seconds < 60:
        return f'0:{value:0>6}'
    return value
