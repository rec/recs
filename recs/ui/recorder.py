import json
import os
import shutil
import sys
import uuid
from collections.abc import Iterator, Mapping, Sequence
from multiprocessing import connection
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError
from reccy import logging
from threa import HasThread, Runnable, Runnables

from recs.base import times
from recs.base.errors import ErrorRecord, RecsError
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.cfg import settings
from recs.cfg.aliases import Aliases
from recs.cfg.cfg import Cfg
from recs.cfg.device import DeviceDict, InputDevice, get_input_devices
from recs.cfg.file_source import FileSource
from recs.cfg.source import Source
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames, validate_track_names
from recs.daemon import external_ipc, gui_ipc, gui_protocol

from . import (
    calibration,
    disk_monitor,
    disk_space,
    gui_process,
    live,
    recording_paths,
    recording_session,
    session_manifest,
)
from .device_poller import DevicePoller
from .full_state import FullState
from .key_events import KeyEvent, make_key_recorder
from .source_process import SourceProcess
from .source_recorder import POLL_TIMEOUT, BufferStats, SourceFailure, SourceUpdate
from .source_tracks import input_device_tracks, source_tracks

FRAME_CLOCK_GRACE = 5.0
MIN_FRAME_CLOCK_RATIO = 0.5
SOURCE_STALL_TIMEOUT = 10.0
LOGGER = logging.get_logger(__name__)
API_COMMANDS = [
    'calibrate',
    'capabilities',
    'disk_status',
    'get_cfg',
    'get_track_names',
    'list_devices',
    'mutable_attributes',
    'mark',
    'pause_recording',
    'reload_profiles',
    'resume_recording',
    'set_key_label',
    'set_noise_floor',
    'set_track_names',
    'set_tracks',
    'set_cfg',
    'shutdown',
    'start_recording',
    'status_snapshot',
    'stop_recording',
]


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
        all_tracks = [
            (source, self._restored_tracks(source, tracks))
            for source, tracks in source_tracks(cfg)
        ]
        self.warnings: list[ErrorRecord] = []
        self.no_devices_reported = False
        self.no_channels_reported = False
        self.recording_paused = False
        self.recording_stopped = False
        self.track_names = saved_settings.track_names
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
        self.external_shutdown_started = False
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
        if isinstance(self.live, gui_ipc.DaemonGuiServer):
            self.live.external_rows = self._publish_external_rows
        self.sources = {
            source.name: SourceProcess(self.cfg, tracks, track_names=self.track_names)
            for source, tracks in all_tracks
        }
        self.frames = dict.fromkeys(self.sources, 0)
        self.buffer_stats: dict[str, BufferStats] = {}
        self.buffer_drops_reported = dict.fromkeys(self.sources, 0)
        self.source_frames_at_start = dict.fromkeys(self.sources, 0)
        self.source_start_times = dict.fromkeys(self.sources, self.state.start_time)
        self.source_last_updates = dict.fromkeys(self.sources, self.state.start_time)
        self.session = recording_session.RecordingSession(
            str(uuid.uuid4()), self.session_start_time
        )
        self.session_stopped = False
        self.key_recorder = make_key_recorder(cfg)
        self.disk_monitor = disk_monitor.DiskMonitor(self.cfg)
        self.failed: set[str] = set()
        self.lag_reported: set[str] = set()
        self.present: set[str] = set()
        self.hardware = {
            name: source
            for name, source in self.sources.items()
            if isinstance(source.source, InputDevice)
        }
        self.files = {
            name: source
            for name, source in self.sources.items()
            if isinstance(source.source, FileSource)
        }
        self.calibration = calibration.Calibration(
            self.cfg,
            self.hardware,
            self._track_for_channel,
            self._receive_connection,
            self._record_event,
            self._set_cfg_value,
        )

        runnables = tuple(self.files.values()) + (self.key_recorder,)
        self.poller = None
        if self.hardware or not self.files:
            self.poller = DevicePoller(cfg.console.sleep_time_device)
            self.poller.poll()
            runnables += (self.poller,)
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

    def rows(self) -> Iterator[dict[str, Any]]:
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
        now = times.timestamp()
        if not self.disk_monitor.ready(now):
            return
        if self.disk_monitor.paused:
            for candidate in self._removable_disks():
                if candidate.free_bytes >= self._disk_threshold(candidate):
                    if self._switch_recording_disk(
                        candidate, 'removable_disk_available'
                    ):
                        self._resume_recording('removable_disk_available', candidate)
                    return
            return
        path = recording_paths.existing_parent(self._manifest_path())
        current = self._recording_disk(path)
        if current is None:
            self._record_warning('Cannot read recording disk space')
            return
        self.disk_monitor.add_sample(now, current)
        rate = self.disk_monitor.rate.bytes_per_second
        for threshold in self.disk_monitor.new_alerts(current):
            self._record_disk_event('disk_space_alert', current, threshold, rate)
            self._record_warning(
                f'Disk space alert on {current.path}: {current.free_bytes} bytes free'
            )

        emergency = self._disk_threshold(current)
        if current.free_bytes < emergency:
            if self.disk_monitor.new_emergency(current):
                self._record_disk_event('disk_space_emergency', current, None, rate)
                self._record_warning(
                    f'Disk space emergency on {current.path}: '
                    f'{current.free_bytes} bytes free'
                )
            self._handle_disk_emergency(current)
            return
        if self.disk_monitor.first_alert and self.cfg.recording.disk_auto_switch:
            candidates = self._removable_disks()
            if candidates and candidates[0].free_bytes > current.free_bytes:
                self._switch_recording_disk(
                    candidates[0], 'new_removable_disk_has_more_space'
                )

    def _disk_threshold(self, disk: disk_space.Disk) -> int:
        return self.disk_monitor.emergency_threshold(disk)

    def _pause_threshold(self, disk: disk_space.Disk) -> int:
        return self.disk_monitor.pause_threshold(disk)

    def _removable_disks(self) -> list[disk_space.Disk]:
        return self.disk_monitor.removable_disks()

    def _recording_disk(self, path: Path) -> disk_space.Disk | None:
        return self.disk_monitor.recording_disk(path)

    def _record_disk_event(
        self, event_type: str, disk: disk_space.Disk, threshold: str | None, rate: float
    ) -> None:
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                type=event_type,
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                path=str(self.cfg.directory.output_directory),
                disk=str(disk.path),
                free_bytes=disk.free_bytes,
                estimated_seconds_remaining=(disk.free_bytes / rate if rate else None),
                threshold=threshold,
                severity='emergency'
                if event_type == 'disk_space_emergency'
                else 'warning',
                disk_kind='removable' if disk.removable else 'system',
            )
        )

    def _handle_disk_emergency(self, current: disk_space.Disk) -> None:
        for candidate in self._removable_disks():
            if (
                candidate.path != current.path
                and not current.path.is_relative_to(candidate.path)
                and candidate.free_bytes >= self._disk_threshold(candidate)
            ):
                self._switch_recording_disk(candidate, 'disk_space_emergency')
                return
        system = disk_space.disk(Path.home(), False)
        if system is not None and system.free_bytes >= self._disk_threshold(system):
            self._switch_recording_disk(system, 'disk_space_emergency')
            return
        if current.free_bytes >= self._pause_threshold(current):
            return
        self._pause_recording('disk_space_exhausted', current)
        self.disk_monitor.paused = True

    def _switch_recording_disk(self, disk: disk_space.Disk, reason: str) -> bool:
        previous = self.cfg.directory.output_directory
        output = recording_paths.available_directory(
            disk.path
            / self.cfg.general.default_record_directory
            / recording_paths.daemon_session_directory_name(times.timestamp())
        )
        try:
            output.mkdir(parents=True)
        except OSError as error:
            self._record_warning(
                f'Cannot switch recording disk to {disk.path}: {error}'
            )
            self._write_manifest_record(
                session_manifest.ManifestEvent(
                    type='disk_switch_failed',
                    timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                    from_path=previous,
                    to_path=str(output),
                    reason=reason,
                )
            )
            return False
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                type='disk_switch_started',
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                from_path=previous,
                to_path=str(output),
                from_free_bytes=shutil.disk_usage(
                    recording_paths.existing_parent(self._manifest_path())
                ).free,
                to_free_bytes=disk.free_bytes,
                reason=reason,
            )
        )
        for source in self.hardware.values():
            source.stop()
            source.join()
        self._receive_pending_updates()
        previous_manifest = (
            self.session.manifest.path if self.session.manifest is not None else None
        )
        next_manifest = (
            recording_paths.manifest_directory(str(output), self.session_start_time)
            / 'recs-session.jsonl'
        )
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                type='disk_switch_finished',
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                from_path=previous,
                to_path=str(output),
                continued_at=str(next_manifest),
            )
        )
        self._finish_manifest()
        self.session.reset(self.session_start_time)
        directory = self.cfg.directory.model_copy(
            update={'output_directory': str(output)}
        )
        self.cfg = self.cfg.model_copy(update={'directory': directory})
        self.cfg.__dict__.pop('output_path_pattern', None)
        for source in self.sources.values():
            source.set_cfg(self.cfg)
        self.session.continued_from = (
            str(previous_manifest) if previous_manifest else None
        )
        self._start_manifest()
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                type='disk_switch_finished',
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                from_path=previous,
                to_path=str(output),
                to_free_bytes=disk.free_bytes,
                reason=reason,
            )
        )
        self._record_warning(f'Switched recording disk to {disk.path}: {reason}')
        self.recording_paused = False
        self.disk_monitor.paused = False
        return True

    def _poll_devices(self) -> None:
        if self.poller is None or (snapshot := self.poller.latest()) is None:
            return

        if snapshot:
            self.no_devices_reported = False
        elif not self.present:
            self._report_no_devices()

        self._add_detected_hardware(snapshot)
        compatible: set[str] = set()
        for name, source in self.hardware.items():
            info = snapshot.get(name)
            if info is None:
                if name in self.present:
                    warning = f'Device {name} went offline'
                    self._record_warning(warning)
                self.failed.discard(name)
                source.stop()
                continue

            channels = int(info['max_input_channels'])
            if channels < source.required_channels:
                source.stop()
                if name not in self.failed:
                    warning = (
                        f'{name} has {channels} input channels; '
                        f'{source.required_channels} required'
                    )
                    self._record_warning(warning)
                    self.failed.add(name)
                continue

            compatible.add(name)
            if name not in self.present:
                self.failed.discard(name)
            if (
                not source.started
                and name not in self.failed
                and not self.recording_paused
                and not self.recording_stopped
                and not self._invocation_expired()
            ):
                source.start()
                self.source_frames_at_start[name] = self.frames[name]
                self.source_start_times[name] = times.timestamp()
                self.source_last_updates[name] = self.source_start_times[name]

        self._record_source_presence(compatible)
        self.present = compatible
        if snapshot and not self.hardware:
            self._report_no_channels()

    def _add_detected_hardware(self, snapshot: dict[str, DeviceDict]) -> None:
        if self.cfg.device.devices.name:
            return
        input_devices = get_input_devices(list(snapshot.values()))
        aliases = Aliases(self.cfg.device.alias, input_devices)
        for source, tracks in input_device_tracks(self.cfg, input_devices):
            if source.name not in self.sources:
                self._add_source(source, self._restored_tracks(source, tracks), aliases)

    def _restored_tracks(
        self, source: Source, defaults: Sequence[Track]
    ) -> Sequence[Track]:
        saved = self.saved_tracks.get(source.name)
        if saved is None:
            return defaults
        expected = {channel for track in defaults for channel in track.channels}
        channels = {channel for track in saved for channel in track.channels}
        if channels != expected:
            return defaults
        try:
            tracks = [Track(source, tuple(track.channels)) for track in saved]
        except RecsError:
            return defaults
        if len(channels) != sum(len(track.channels) for track in tracks):
            return defaults
        return sorted(tracks, key=lambda track: track.channels)

    def _add_source(
        self,
        source: InputDevice,
        tracks: Sequence[Track],
        aliases: Aliases,
    ) -> None:
        source_process = SourceProcess(self.cfg, tracks, track_names=self.track_names)
        self.sources[source.name] = source_process
        self.hardware[source.name] = source_process
        self.frames[source.name] = 0
        self.buffer_drops_reported[source.name] = 0
        self.source_frames_at_start[source.name] = 0
        self.source_start_times[source.name] = self.state.start_time
        self.source_last_updates[source.name] = self.state.start_time
        self.state.add_source(source, tracks, aliases)
        self.no_channels_reported = False

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

    def _record_source_presence(self, compatible: set[str]) -> None:
        for name in sorted(compatible - self.present):
            self._record_event(
                'source_online',
                source=name,
                start_frame=self.source_frames_at_start[name],
            )
        for name in sorted(self.present - compatible):
            self._record_active_tracks_stopped(name)
            self._record_event('source_offline', source=name)

    def _record_active_tracks_stopped(self, source_name: str) -> None:
        for track_name, channel_state in self.state.state[source_name].items():
            if channel_state.is_active:
                self._record_event(
                    'track_stopped',
                    source=source_name,
                    track=track_name,
                )

    def _reap_sources(self) -> None:
        for name, source in self.sources.items():
            if not source.started or source.is_alive:
                continue
            self._drain(source.connection)
            expected = not source.running
            source.join(timeout=0)
            for update in source.take_updates():
                self._receive_source_message(update)
            if name not in self.hardware:
                continue

            if not expected and name in self.present:
                self.failed.add(name)

    def _stop_stalled_sources(self) -> None:
        now = times.timestamp()
        for name, source in self.sources.items():
            if not source.started or not source.is_alive or not source.running:
                continue
            if now - self.source_last_updates[name] <= SOURCE_STALL_TIMEOUT:
                continue
            warning = f'Device {name} stopped sending updates'
            self._record_warning(warning)
            source.stop()
            source.join()
            if name in self.hardware:
                self.failed.add(name)

    def _receive_pending_updates(self) -> None:
        self._receive_key_events()
        for source in self.sources.values():
            for update in source.take_updates():
                self._receive_source_message(update)

    def _receive_key_events(self) -> None:
        for event in self.key_recorder.take_events():
            self._record_key_event(event)
        if self.live is None:
            return
        for event in self.live.take_key_events():
            self._record_key_event(event)

    def _receive_control_requests(self) -> None:
        if isinstance(self.live, gui_ipc.DaemonGuiServer):
            for error in self.live.take_protocol_errors():
                self._record_warning(f'Malformed GUI protocol message: {error}')
        requests = (
            cast(list[gui_ipc.ControlRequest], self.live.take_control_requests())
            if self.live is not None
            else []
        )
        for request in requests:
            try:
                response = self._handle_control_request(request.request)
            except RecsError as e:
                request.respond(gui_protocol.Error(type='error', message=str(e)))
            else:
                request.respond(response)
        if self.external is None:
            return
        for request in self.external.take_requests():
            try:
                external_request = external_ipc.recs_request(request.request)
                if isinstance(external_request, gui_protocol.Shutdown):
                    if not self.external_shutdown_started:
                        self.external_shutdown_started = True
                        self.stop()
                    response = gui_protocol.RecordingState(
                        type='recording_state', paused=False, stopped=True
                    )
                else:
                    response = self._handle_control_request(external_request)
            except (RecsError, ValidationError) as e:
                self._record_warning(f'External Recs protocol error: {e}')
                response = gui_protocol.Error(type='error', message=str(e))
            self.external.respond(
                request, external_ipc.response(request.request, response)
            )

    def _publish_external_rows(
        self,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        if self.external is None:
            return
        self.external.publish_rows(rows, errors)

    def _handle_control_request(
        self,
        request: gui_protocol.Request,
    ) -> gui_protocol.Response:
        if isinstance(request, gui_protocol.Calibrate):
            return self._calibrate_noise_floor(request)
        if isinstance(request, gui_protocol.Capabilities):
            return gui_protocol.CapabilitiesResult(
                type='capabilities_result',
                commands=API_COMMANDS,
                version=gui_protocol.VERSION,
            )
        if isinstance(request, gui_protocol.DiskStatusRequest):
            return self._disk_status()
        if isinstance(request, gui_protocol.GetCfg):
            return self._get_cfg(request)
        if isinstance(request, gui_protocol.GetTrackNames):
            return gui_protocol.TrackNames(
                type='track_names', track_names=self.track_names
            )
        if isinstance(request, gui_protocol.ListDevices):
            return gui_protocol.Devices(type='devices', devices=self._device_status())
        if isinstance(request, gui_protocol.MutableAttributes):
            return gui_protocol.MutableAttributesResult(
                type='mutable_attributes_result',
                mutable_attributes=sorted(self.cfg.mutable_attributes),
            )
        if isinstance(request, gui_protocol.Mark):
            return self._mark(request)
        if isinstance(request, gui_protocol.PauseRecording):
            return self._pause_recording('pause_recording')
        if isinstance(request, gui_protocol.ReloadProfiles):
            return self._reload_profiles()
        if isinstance(request, gui_protocol.ResumeRecording):
            return self._resume_recording('resume_recording')
        if isinstance(request, gui_protocol.SetCfg):
            return self._set_cfg(request)
        if isinstance(request, gui_protocol.SetKeyLabel):
            return self._set_key_label(request)
        if isinstance(request, gui_protocol.SetNoiseFloor):
            return self._set_noise_floor(request)
        if isinstance(request, gui_protocol.SetTrackNames):
            return self._set_track_names(request)
        if isinstance(request, gui_protocol.SetTracks):
            return self._set_tracks(request)
        if isinstance(request, gui_protocol.StartRecording):
            return self._resume_recording('start_recording')
        if isinstance(request, gui_protocol.StatusSnapshotRequest):
            return self._status_snapshot()
        if isinstance(request, gui_protocol.StopRecording):
            return self._stop_recording()
        raise RecsError(f'Unsupported request: {request.type}')

    def _mark(self, request: gui_protocol.Mark) -> gui_protocol.Marked:
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type='mark',
                label=request.label,
            )
        )
        return gui_protocol.Marked(type='marked', label=request.label)

    def _pause_recording(
        self, reason: str, disk: disk_space.Disk | None = None
    ) -> gui_protocol.RecordingState:
        self.recording_paused = True
        for source in self.hardware.values():
            if source.running:
                source.stop()
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type='recording_paused',
                label=reason,
                reason=reason,
                current_path=str(self.cfg.directory.output_directory),
                free_bytes=disk.free_bytes if disk else None,
            )
        )
        return self._recording_state()

    def _resume_recording(
        self, reason: str, disk: disk_space.Disk | None = None
    ) -> gui_protocol.RecordingState:
        if self.session_stopped:
            self._start_recording_session()
        self.recording_paused = False
        self.recording_stopped = False
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type='recording_resumed',
                label=reason,
                reason=reason,
                path=str(self.cfg.directory.output_directory),
                free_bytes=disk.free_bytes if disk else None,
            )
        )
        return self._recording_state()

    def _stop_recording(self) -> gui_protocol.RecordingState:
        if self.recording_stopped:
            return self._recording_state()
        self._pause_recording('stop_recording')
        self.recording_stopped = True
        self.session_stopped = self.session.manifest is not None
        if self.session_stopped:
            for source in self.hardware.values():
                source.join()
            self._receive_pending_updates()
            self._finish_manifest()
        return self._recording_state()

    def _set_key_label(
        self, request: gui_protocol.SetKeyLabel
    ) -> gui_protocol.KeyLabelSet:
        labels = self.cfg.keys.labels | {request.key: request.label}
        self._set_cfg_value(
            'keys.key_label', [f'{key}={label}' for key, label in labels.items()]
        )
        return gui_protocol.KeyLabelSet(
            type='key_label_set', key=request.key, label=request.label
        )

    def _set_noise_floor(
        self, request: gui_protocol.SetNoiseFloor
    ) -> gui_protocol.NoiseFloorSet:
        track = self._track_for_channel(request.source, request.channel)
        floors = {
            source: dict(channels)
            for source, channels in self.cfg.recording.channel_noise_floors.items()
        }
        floors.setdefault(request.source, {})[track.name] = request.noise_floor
        self._set_cfg_value('recording.channel_noise_floors', floors)
        return gui_protocol.NoiseFloorSet(
            type='noise_floor_set',
            source=request.source,
            channel=request.channel,
            noise_floor=request.noise_floor,
        )

    def _set_track_names(
        self, request: gui_protocol.SetTrackNames
    ) -> gui_protocol.TrackNames:
        try:
            track_names = validate_track_names(request.track_names)
        except ValueError as e:
            raise RecsError(str(e)) from None
        self.track_names = {
            device: dict(names) for device, names in track_names.items()
        }
        for source in self.sources.values():
            source.set_track_names(self.track_names)
        self.state.set_track_names(self.track_names)
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type='track_names_set',
                value=self.track_names,
            )
        )
        self._save_settings()
        return gui_protocol.TrackNames(type='track_names', track_names=self.track_names)

    def _set_tracks(self, request: gui_protocol.SetTracks) -> gui_protocol.TracksSet:
        source = self.hardware.get(request.source)
        if source is None:
            raise RecsError(f'Unknown input device: {request.source}')
        tracks = self._updated_tracks(source, request.tracks)
        names = self._updated_track_names(request.source, request.tracks)
        floors = self._updated_track_noise_floors(source, request.tracks)
        if floors != self.cfg.recording.channel_noise_floors:
            self._set_cfg_value('recording.channel_noise_floors', floors, save=False)
        self.track_names = names
        source.set_tracks(tracks, names)
        self.saved_tracks[source.name] = [
            settings.TrackSettings(channels=list(track.channels)) for track in tracks
        ]
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type='tracks_set',
                source=request.source,
                value=[track.model_dump() for track in request.tracks],
            )
        )
        self._save_settings()
        return gui_protocol.TracksSet(
            type='tracks_set', source=request.source, tracks=request.tracks
        )

    def _updated_tracks(
        self,
        source: SourceProcess,
        requested: list[gui_protocol.ChannelTrack],
    ) -> list[Track]:
        if not requested:
            raise RecsError('At least one track is required')
        channels: list[int] = []
        new_tracks: list[Track] = []
        for definition in requested:
            values = definition.channels
            if len(values) not in (1, 2):
                raise RecsError('Tracks must be mono or stereo')
            if values != sorted(values) or len(set(values)) != len(values):
                raise RecsError('Track channels must be in ascending order')
            if len(values) == 2 and values[1] != values[0] + 1:
                raise RecsError('Stereo channels must be adjacent')
            if values[0] <= 0 or values[-1] > source.source.channels:
                raise RecsError(f'Invalid channel for device {source.name}')
            try:
                track = Track(source.source, tuple(values))
            except RecsError as e:
                raise RecsError(str(e)) from None
            channels.extend(values)
            new_tracks.append(track)

        if len(channels) != len(set(channels)):
            raise RecsError('Tracks cannot share channels')
        selected = set(channels)
        for track in source.tracks:
            overlap = selected & set(track.channels)
            if overlap and overlap != set(track.channels):
                raise RecsError(f'All channels in {track} must be replaced together')
        remaining = [
            track for track in source.tracks if not (selected & set(track.channels))
        ]
        return sorted([*remaining, *new_tracks], key=lambda track: track.channels)

    def _updated_track_names(
        self,
        source_name: str,
        requested: list[gui_protocol.ChannelTrack],
    ) -> DeviceTrackNames:
        names = {device: dict(values) for device, values in self.track_names.items()}
        changed = {channel for track in requested for channel in track.channels}
        device_names = names.setdefault(source_name, {})
        for name, channel in list(device_names.items()):
            if channel in changed:
                del device_names[name]
        for track in requested:
            if not track.name:
                continue
            if track.name in device_names:
                raise RecsError(f'Duplicate track name: {track.name}')
            device_names[track.name] = track.channels[0]
        if not device_names:
            del names[source_name]
        try:
            return validate_track_names(names)
        except ValueError as e:
            raise RecsError(str(e)) from None

    def _updated_track_noise_floors(
        self,
        source: SourceProcess,
        requested: list[gui_protocol.ChannelTrack],
    ) -> dict[str, dict[str, float | None]]:
        floors = {
            device: dict(values)
            for device, values in self.cfg.recording.channel_noise_floors.items()
        }
        device_floors = floors.setdefault(source.name, {})
        changed = {channel for track in requested for channel in track.channels}
        replaced = [track for track in source.tracks if changed & set(track.channels)]
        values = {track.name: device_floors.pop(track.name, None) for track in replaced}
        for definition in requested:
            matching = [
                value
                for track, value in values.items()
                if set(_track_channels(track)) & set(definition.channels)
            ]
            if len(set(matching)) > 1:
                raise RecsError(
                    'Cannot pair channels with different noise floors: '
                    f'{definition.channels}'
                )
            if matching:
                device_floors[_track_name(definition.channels)] = matching[0]
        if not device_floors:
            del floors[source.name]
        return floors

    def _get_cfg(self, request: gui_protocol.GetCfg) -> gui_protocol.CfgValue:
        try:
            value = self.cfg.get_attr(request.address)
        except ValueError as e:
            raise RecsError(str(e)) from None
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type='cfg_get',
                address=request.address,
                value=value,
            )
        )
        return gui_protocol.CfgValue(
            type='cfg_value', address=request.address, value=value
        )

    def _set_cfg(self, request: gui_protocol.SetCfg) -> gui_protocol.CfgSet:
        value = self._set_cfg_value(request.address, request.value)
        return gui_protocol.CfgSet(type='cfg_set', address=request.address, value=value)

    def _set_cfg_value(
        self, address: str, value: object, *, save: bool = True
    ) -> object:
        try:
            self.cfg = self.cfg.set_attr(address, value)
        except ValueError as e:
            raise RecsError(str(e)) from None
        self.calibration.cfg = self.cfg
        value = self.cfg.get_attr(address)
        for source in self.sources.values():
            source.set_cfg(self.cfg)
        self._write_manifest_record(
            session_manifest.ManifestEvent(
                timestamp=session_manifest.timestamp_to_json(times.timestamp()),
                type='cfg_set',
                address=address,
                value=value,
            )
        )
        if save:
            self._save_settings()
        return value

    def _save_settings(self) -> None:
        if self.cfg.save_settings:
            settings.save(self.cfg, self.track_names, self.saved_tracks)

    def _reload_profiles(self) -> gui_protocol.ProfilesReloaded:
        if not self.cfg.device.profiles.name:
            raise RecsError('Cannot reload profiles without --profiles')
        self.cfg.__dict__.pop('device_profiles', None)
        for source in self.sources.values():
            source.cfg = self.cfg
        return gui_protocol.ProfilesReloaded(
            type='profiles_reloaded', profiles_path=str(self.cfg.device.profiles)
        )

    def _status_snapshot(self) -> gui_protocol.StatusSnapshot:
        return gui_protocol.StatusSnapshot(
            type='status_snapshot_result',
            disk=self._disk_status().model_dump(exclude={'type'}),
            devices=self._device_status(),
            errors=self.error_records(),
            recording=self._recording_state().model_dump(exclude={'type'}),
            rows=list(self.rows()),
        )

    def _disk_status(self) -> gui_protocol.DiskStatus:
        path = recording_paths.existing_parent(self._manifest_path()).resolve()
        usage = shutil.disk_usage(path)
        resume_disk = next(
            (
                disk.path
                for disk in self._removable_disks()
                if disk.free_bytes >= self._disk_threshold(disk)
            ),
            None,
        )
        return gui_protocol.DiskStatus(
            type='disk_status_result',
            free_bytes=usage.free,
            path=str(path),
            total_bytes=usage.total,
            used_bytes=usage.used,
            estimated_seconds_remaining=(
                usage.free / self.disk_monitor.rate.bytes_per_second
                if self.disk_monitor.rate.bytes_per_second
                else None
            ),
            alert_threshold=self.disk_monitor.alert_threshold,
            alert_active=self.disk_monitor.first_alert,
            automatic_switch_armed=(
                self.disk_monitor.first_alert and self.cfg.recording.disk_auto_switch
            ),
            paused_for_disk_space=self.disk_monitor.paused,
            resume_disk=str(resume_disk) if resume_disk else None,
        )

    def _device_status(self) -> list[dict[str, object]]:
        devices: list[dict[str, object]] = []
        for name, source in sorted(self.sources.items()):
            device = source.source
            devices.append(
                {
                    'channels': device.channels,
                    'name': name,
                    'online': name in self.present,
                    'sample_rate': device.samplerate,
                }
            )
        return devices

    def _recording_state(self) -> gui_protocol.RecordingState:
        return gui_protocol.RecordingState(
            type='recording_state',
            paused=self.recording_paused,
            stopped=self.recording_stopped,
        )

    def _drain(self, conn: connection.Connection) -> None:
        while _connection_ready(conn):
            if not self._receive_connection(conn):
                break

    def _receive_connection(self, conn: connection.Connection) -> bool:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return False
        self._receive_source_message(cast(SourceUpdate | SourceFailure, msg))
        return True

    def _receive_source_message(self, message: SourceUpdate | SourceFailure) -> None:
        if isinstance(message, SourceFailure):
            warning = f'Device {message.source_name} failed: {message.message}'
            self._record_warning(warning)
            self.failed.add(message.source_name)
            return
        self._receive_update(message)

    def _receive_update(self, update: SourceUpdate) -> None:
        self.frames[update.source_name] += update.frames
        self._record_buffer_status(update)
        self.session.record_files(
            update.files,
            update.file_end_frames or {},
            update.file_end_timestamps or {},
        )
        for file_record in update.file_records or []:
            self.session.record_file_started(
                file_record, self._manifest_source(file_record.source_name)
            )
        source = self.sources[update.source_name]
        if update.track_layout is not None:
            self.state.replace_source(source.source, source.tracks, self.cfg.aliases)
            self.state.set_track_names(self.track_names)
        previous = {
            track_name: state.is_active
            for track_name, state in self.state.state[update.source_name].items()
        }
        self.state.update({update.source_name: update.channels})
        self._record_track_activity(
            update.source_name,
            previous,
            update.channels,
            update.frame_count,
            update.timestamp,
        )
        now = times.timestamp()
        self.source_last_updates[update.source_name] = now
        if update.calibration is not None:
            self.calibration.results[update.source_name] = update.calibration
        if source.running and not self._source_frame_clock_valid(source, now):
            source.stop()
            self.failed.add(update.source_name)
            return
        if source.running and self._source_time_expired(source):
            source.stop()

    def _record_buffer_status(self, update: SourceUpdate) -> None:
        if update.buffer_stats is not None:
            self.buffer_stats[update.source_name] = update.buffer_stats
            reported = self.buffer_drops_reported[update.source_name]
            if update.buffer_stats.dropped_frames > reported:
                self._write_manifest_record(
                    session_manifest.ManifestEvent(
                        type='buffer_overflow',
                        timestamp=session_manifest.timestamp_to_json(
                            update.buffer_stats.last_drop_timestamp
                        ),
                        source=update.source_name,
                        dropped_blocks=update.buffer_stats.dropped_blocks,
                        dropped_frames=update.buffer_stats.dropped_frames,
                        max_queued_seconds=update.buffer_stats.max_queued_seconds,
                        queued_seconds=update.buffer_stats.queued_seconds,
                    )
                )
                self.buffer_drops_reported[
                    update.source_name
                ] = update.buffer_stats.dropped_frames
        for warning in update.buffer_warnings or []:
            self._record_warning(warning)

    def _source_frame_clock_valid(self, source: SourceProcess, now: float) -> bool:
        if source.name not in self.hardware:
            return True

        elapsed = now - self.source_start_times[source.name]
        if elapsed < FRAME_CLOCK_GRACE:
            return True

        frames = self.frames[source.name] - self.source_frames_at_start[source.name]
        recorded = frames / source.source.samplerate
        if recorded >= elapsed * MIN_FRAME_CLOCK_RATIO:
            return True

        if source.name not in self.lag_reported:
            warning = f'Device {source.name} lagging behind real time'
            self._record_warning(warning)
            self.lag_reported.add(source.name)
        return False

    def _record_track_activity(
        self,
        source_name: str,
        previous: dict[str, bool],
        updates: Mapping[str, Any],
        frame_count: int | None,
        timestamp: float | None,
    ) -> None:
        for track_name in updates:
            active = self.state.state[source_name][track_name].is_active
            was_active = previous[track_name]
            if active == was_active:
                continue
            event_type = 'track_started' if active else 'track_stopped'
            self._record_event(
                event_type,
                source=source_name,
                track=track_name,
                frame_count=frame_count,
                timestamp=timestamp,
            )

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

    def _source_time_expired(self, source: SourceProcess) -> bool:
        total = self.cfg.recording.total_run_time
        if not total:
            return False

        target = round(total * source.source.samplerate)
        return self.frames[source.name] >= target

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
        self._start_manifest()
        self.session_stopped = False

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

    def _manifest_source(self, source_name: str) -> str | None:
        if isinstance(self.sources[source_name].source, FileSource):
            return source_name
        return None

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

    def _calibrate_noise_floor(
        self, request: gui_protocol.Calibrate
    ) -> gui_protocol.Calibrated:
        return self.calibration.calibrate(request)

    def _track_for_channel(self, source_name: str, channel: int) -> Track:
        source = self.hardware.get(source_name)
        if source is None:
            raise RecsError(f'Unknown input device: {source_name}')
        if channel <= 0:
            raise RecsError('Channel must be positive')
        for track in source.tracks:
            if channel in track.channels:
                return track
        raise RecsError(f'Device {source_name} has no selected channel {channel}')

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


def _connection_ready(conn: connection.Connection) -> bool:
    try:
        return conn.poll()
    except OSError:
        return False


def _track_channels(track_name: str) -> list[int]:
    return [int(channel) for channel in track_name.split('-') if channel]


def _track_name(channels: list[int]) -> str:
    return '-'.join(str(channel) for channel in channels)
