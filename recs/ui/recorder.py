import json
import os
import sys
import uuid
from collections.abc import Iterator, Sequence
from multiprocessing import connection
from pathlib import Path
from time import monotonic
from typing import cast

from reccy.runtime import logging
from threa import HasThread, Runnable, Runnables

from recs.base import times
from recs.base.errors import ErrorRecord, RecsError
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.base.waveform import WaveformBatchData, WaveformLayoutData
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.cfg.file_source import FileSource
from recs.cfg.source import Source
from recs.cfg.track import Track
from recs.daemon import external_ipc, gui_ipc, gui_protocol
from recs.midi.recorder import MidiRecorder
from recs.osc.recorder import OscRecorder

from . import (
    calibration,
    card_replacement,
    device_lifecycle,
    disk_space_controller,
    disk_space_policy,
    gui_process,
    live,
    recording_control,
    recording_control_protocol,
    recording_paths,
    recording_session,
    recovery_report,
    session_record,
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
        self.awaiting_card: ErrorRecord | None = None
        self._output_unmounted = False
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
        self.session_directory = recording_paths.session_directory(
            self.cfg.directory.output_directory, self.session_start_time
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
        session_id = str(uuid.uuid4())
        self.session = recording_session.RecordingSession(
            session_id, self.session_start_time
        )
        self._midi = MidiRecorder(
            self.cfg,
            recording_paths.media_session_directory(self.session_directory, 'midi'),
            self._record_warning,
            self.session.write,
            write_error=self._record_write_error,
        )
        self._osc = OscRecorder(
            self.cfg,
            recording_paths.media_session_directory(self.session_directory, 'osc'),
            self._record_warning,
            self.session.write,
            self._record_write_error,
        )
        self.key_recorder = make_key_recorder(cfg)
        self._disk_space_policy = disk_space_policy.DiskSpacePolicy(self.cfg)
        self._devices = device_lifecycle.DeviceLifecycle(
            self.cfg,
            self.state,
            self.session_directory,
            self.saved_tracks,
            track_names,
            all_tracks,
            self._record_warning,
            self._record_event,
            self._record_device_file_update,
            self._record_calibration_result,
            self._record_device_buffer_update,
            self._record_write_error,
            SourceProcess,
            DevicePoller,
            waveform_update=self._publish_live_waveforms,
        )
        self._control = recording_control.RecordingControl(
            self.cfg,
            self.saved_tracks,
            track_names,
            self.state,
            self.session,
            self._devices,
            self._disk_space_policy,
            lambda record: self._write_record_entry(record),
            self._replace_cfg,
            lambda: list(self.rows()),
            self.error_records,
            self._midi.status,
            self._osc.status,
            self._record_path,
            self._receive_pending_updates,
            self._finish_record,
            self._card_replace,
        )
        self._card_replacement = card_replacement.CardReplacement()
        self._recording_disk = recording_paths.mounted_disk(self.session_directory)
        self._calibration = calibration.Calibration(
            self.cfg,
            self._devices.hardware,
            self._control.track_for_channel,
            self._receive_connection,
            self._record_event,
            self._control.set_cfg_value,
        )
        self._control.calibrate = self._calibration.calibrate
        self._disk_space_controller = disk_space_controller.DiskSpaceController(
            self.cfg,
            self.session,
            self._devices,
            self._disk_space_policy,
            self._control,
            lambda record: self._write_record_entry(record),
            self._record_warning,
            self._replace_cfg,
            self._receive_pending_updates,
            self._start_record,
            self._finish_record,
            self._record_path,
            lambda: self.session_start_time,
        )
        if isinstance(self.live, gui_ipc.DaemonGuiServer):
            self.live.external_rows = self._publish_external_rows

        runnables = tuple(self._devices.files.values()) + (
            self._midi,
            self._osc,
            self.key_recorder,
        )
        if self._devices.poller is not None:
            runnables += (self._devices.poller,)
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

    def _record_device_file_update(
        self, update: SourceUpdate, source: SourceProcess
    ) -> None:
        if not self._output_unmounted:
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
            self.state.set_track_names(self._control.track_names)

    def _record_calibration_result(self, source: str, values: dict[str, float]) -> None:
        self._calibration.results[source] = values

    def _record_device_buffer_update(self, source: str, stats: BufferStats) -> None:
        self._write_record_entry(
            session_record.EventRecord(
                type='buffer_overflow' if stats.dropped_frames else 'buffer_pressure',
                timestamp=session_record.timestamp_to_json(stats.last_drop_timestamp),
                source=source,
                dropped_blocks=stats.dropped_blocks,
                dropped_frames=stats.dropped_frames,
                max_queued_seconds=stats.max_queued_seconds,
                max_write_seconds=stats.max_write_seconds or None,
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
                    if name == device and (
                        stats := self._devices.buffer_stats.get(source)
                    ):
                        row |= {
                            'buffer': stats.queued_seconds,
                            'dropped': stats.dropped_frames,
                        }
            yield row

    def error_messages(self) -> list[str]:
        return [warning.message for warning in self.warnings]

    def error_records(self) -> list[ErrorRecord]:
        record_errors = [
            ErrorRecord(
                timestamp=session_record.timestamp_to_json(times.timestamp()),
                message=message,
            )
            for message in self.session.record_errors
        ]
        return [
            *self.warnings,
            *([self.awaiting_card] if self.awaiting_card is not None else []),
            *record_errors,
        ]

    def _record_startup_input_errors(
        self,
        all_tracks: Sequence[tuple[Source, Sequence[Track]]],
    ) -> None:
        if self._devices.files:
            return
        if not self.cfg.input_devices:
            if not self.cfg.selection.include:
                self._report_no_devices()
        elif not all_tracks:
            included = self.cfg.aliases.to_tracks(
                self.cfg.selection.include, allow_missing=True
            )
            if included or not self.cfg.selection.include:
                self._report_no_channels()

    def run(self) -> None:
        with raise_keyboard_interrupt_on_signal():
            try:
                self._start_record()
                self._run()
            except KeyboardInterrupt:
                print('Interrupted', file=sys.stderr)
            finally:
                if self.external is not None:
                    self.external.close()
                self._receive_pending_updates()
                self._finish_record()
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
        if self._devices.failed:
            return f'sources failed: {", ".join(sorted(self._devices.failed))}'
        if self.session.files_written:
            return 'all candidate files were removed or are no longer present'
        if not any(self._devices.frames.values()):
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
                    if not self._monitor_card_replacement():
                        self._monitor_disk_space()
                    self._receive_key_events()
                    self._receive_control_requests()
                    self._midi.poll()
                    self._osc.poll()
                    self._poll_devices()
                    self._reap_sources()
                    self._stop_stalled_sources()
                    sources = [
                        source
                        for source in self._devices.sources.values()
                        if source.is_alive
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
                for source in self._devices.hardware.values():
                    source.stop()
                for source in self._devices.hardware.values():
                    source.join()

    def _done(self, sources: Sequence[SourceProcess]) -> bool:
        if self._devices.files and not self._devices.hardware:
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
        if disk := recording_paths.mounted_disk(self.session_directory):
            self._recording_disk = disk
        self._disk_space_controller.monitor_disk_space()

    def _record_write_error(self, source: str, error: str) -> None:
        if self._card_replacement.active:
            return
        old_mount = self._recording_disk
        if old_mount is None or any(
            disk.uuid == old_mount.uuid
            for disk in recording_paths.mounted_disks_with_uuid()
        ):
            self._record_warning(f'Device {source} write failed: {error}')
            return
        self._card_replacement.start_after_unmount(
            self.cfg,
            Path(self.cfg.directory.output_directory),
            old_mount,
            times.timestamp(),
        )
        self._set_awaiting_card(True)
        self._output_unmounted = True
        self._devices.set_writing_enabled(False)
        self._midi.suspend_after_unmount()
        self._osc.suspend_after_unmount()
        self._monitor_card_replacement()
        LOGGER.error(
            'Device %s write failed after %s was unmounted: %s',
            source,
            old_mount.path,
            error,
        )

    def _card_replace(self) -> gui_protocol.CardReplaceStarted:
        result = self._card_replacement.start(
            self.cfg, self.session_directory, times.timestamp()
        )
        self._set_awaiting_card(True)
        self._devices.set_writing_enabled(False)
        deadline = monotonic() + external_ipc.EXTERNAL_RESPONSE_TIMEOUT
        while not self._devices.writing_is_suspended:
            connections = [
                source.connection
                for source in self._devices.sources.values()
                if source.is_alive
            ]
            if connections:
                for conn in connection.wait(connections, timeout=POLL_TIMEOUT):
                    self._receive_connection(cast(connection.Connection, conn))
            if monotonic() >= deadline:
                self._devices.set_writing_enabled(True)
                self._card_replacement.active = False
                self._set_awaiting_card(False)
                raise RecsError('Timed out closing audio files for card replacement')
        self._midi.suspend_for_card_replace()
        self._osc.suspend_for_card_replace()
        self._write_record_entry(
            session_record.EventRecord(
                type='card_replace_started',
                timestamp=session_record.timestamp_to_json(times.timestamp()),
                disk=str(result.old_mount),
                disk_uuid=result.old_uuid,
            )
        )
        self._finish_record()
        self._monitor_card_replacement()
        return result

    def _replacement_disk_uuids(self) -> set[str]:
        mounts = {
            disk.path.resolve(): disk.uuid
            for disk in recording_paths.mounted_disks_with_uuid()
        }
        return {
            mounts[disk.path.resolve()]
            for disk in self._disk_space_policy.removable_disks()
            if disk.free_bytes >= self._disk_space_policy.emergency_threshold(disk)
            and disk.path.resolve() in mounts
        }

    def _monitor_card_replacement(self) -> bool:
        if not self._card_replacement.active:
            return False
        if (
            destination := self._card_replacement.destination(
                self.cfg,
                times.timestamp(),
                self._replacement_disk_uuids(),
            )
        ) is None:
            return self._card_replacement.active
        timestamp = times.timestamp()
        self.session_start_time = timestamp
        self.session.reset(timestamp)
        self._set_session_directory(
            recording_paths.session_directory(
                str(destination.output_directory), timestamp
            )
        )
        self._devices.set_runtime_output_directory(destination.output_directory)
        self._recording_disk = recording_paths.mounted_disk(
            destination.output_directory
        )
        self._output_unmounted = False
        self._set_awaiting_card(False)
        self._start_record()
        self._write_record_entry(
            session_record.EventRecord(
                type='card_replace_finished',
                timestamp=session_record.timestamp_to_json(timestamp),
                to_path=str(destination.output_directory),
                reason=destination.reason,
            )
        )
        self._devices.set_writing_enabled(True)
        return False

    def _poll_devices(self) -> None:
        self._devices.poll(
            self._control.recording_paused,
            self._invocation_expired(),
        )

    def _report_no_devices(self) -> None:
        if self._devices.no_devices_reported:
            return
        warning = 'No input devices detected'
        self._record_warning(warning)
        self._devices.no_devices_reported = True

    def _report_no_channels(self) -> None:
        if self._devices.no_channels_reported:
            return
        warning = 'No channels selected'
        self._record_warning(warning)
        self._devices.no_channels_reported = True

    def _reap_sources(self) -> None:
        self._devices.reap()

    def _stop_stalled_sources(self) -> None:
        self._devices.stop_stalled()

    def _receive_pending_updates(self) -> None:
        self._receive_key_events()
        self._devices.receive_pending_updates()

    def _receive_key_events(self) -> None:
        for event in self.key_recorder.take_events():
            self._record_key_event(event)
        if self.live is None:
            return
        for event in self.live.take_key_events():
            self._record_key_event(event)

    def _receive_control_requests(self) -> None:
        self._control.protocol.receive(
            cast(recording_control_protocol.ControlDisplay | None, self.live),
            self.external,
            self._record_warning,
            self.stop,
        )

    def _publish_live_waveforms(
        self,
        layout: WaveformLayoutData | None,
        batches: list[WaveformBatchData],
    ) -> None:
        if self.external is not None:
            self.external.publish_waveforms(layout, batches)

    def _publish_external_rows(
        self,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        self._control.protocol.publish(self.external, rows, errors)

    def _receive_connection(self, conn: connection.Connection) -> bool:
        return self._devices.receive_connection(conn)

    def _receive_source_message(self, message: SourceUpdate | SourceFailure) -> None:
        self._devices.receive_message(message)

    def _receive_update(self, update: SourceUpdate) -> None:
        self._devices.receive_message(update)

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
        self._write_record_entry(
            session_record.EventRecord(
                timestamp=session_record.timestamp_to_json(
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
        self._write_record_entry(
            session_record.EventRecord(
                timestamp=session_record.timestamp_to_json(times.timestamp()),
                type=event.type,
                key=event.key,
                label=self.cfg.keys.labels.get(event.key),
            )
        )

    def _start_record(self) -> None:
        if not self.cfg.general.dry_run and not self.cfg.general.silence_preview:
            recovery_report.report_unfinished_sessions(
                recording_paths.recovery_root(self.cfg.directory.output_directory)
            )
        self.session.start(
            self.session_directory / 'session-record.jsonl',
            dry_run=self.cfg.general.dry_run,
            silence_preview=self.cfg.general.silence_preview,
        )
        if self.cfg.midi.record_midi:
            self._midi.open_session(
                recording_paths.media_session_directory(self.session_directory, 'midi')
            )
        if self.cfg.osc.osc_nodes.name:
            self._osc.open_session(
                recording_paths.media_session_directory(self.session_directory, 'osc')
            )

    def _finish_record(self) -> None:
        self._midi.close_session()
        self._osc.close_session()
        timestamp = times.timestamp()
        self.session.finish(timestamp)

    def _replace_cfg(self, cfg: Cfg) -> None:
        output_directory_changed = (
            cfg.directory.output_directory != self.cfg.directory.output_directory
        )
        self.cfg = cfg
        self._devices.cfg = cfg
        self._disk_space_policy.cfg = cfg
        self._disk_space_controller.cfg = cfg
        self._calibration.cfg = cfg
        if output_directory_changed:
            self._devices.set_runtime_output_directory(None)
            self._set_session_directory(
                recording_paths.session_directory(
                    self.cfg.directory.output_directory, self.session_start_time
                )
            )

    def _set_session_directory(self, session_directory: Path) -> None:
        self.session_directory = session_directory
        self._devices.set_session_directory(session_directory)
        self._midi.session_directory = recording_paths.media_session_directory(
            session_directory, 'midi'
        )
        self._osc.session_directory = recording_paths.media_session_directory(
            session_directory, 'osc'
        )

    def _record_warning(self, warning: str) -> None:
        timestamp = session_record.timestamp_to_json(times.timestamp())
        LOGGER.error('%s', warning)
        self.warnings.append(ErrorRecord(timestamp=timestamp, message=warning))
        if not self._output_unmounted:
            self.session.write(
                session_record.WarningRecord(
                    timestamp=timestamp,
                    message=warning,
                )
            )

    def _set_awaiting_card(self, value: bool) -> None:
        self.awaiting_card = ErrorRecord(
            timestamp=session_record.timestamp_to_json(times.timestamp()),
            message='awaiting card',
            value=value,
        )

    def _write_record_entry(
        self,
        record: session_record.EventRecord
        | session_record.FileRecord
        | session_record.SessionFooter
        | session_record.WarningRecord,
    ) -> None:
        if self._output_unmounted:
            return
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

    def _record_path(self) -> Path:
        return self.session_directory / 'session-record.jsonl'

    def _output_folder(self) -> Path:
        paths = sorted(path for path in self.session.files_written if path.exists())
        if paths:
            return Path(os.path.commonpath([path.parent for path in paths]))
        return recording_paths.existing_parent(self._record_path()).resolve()


def _summary_time(seconds: float) -> str:
    value = times.to_str(seconds)
    if seconds < 60:
        return f'0:{value:0>6}'
    return value
