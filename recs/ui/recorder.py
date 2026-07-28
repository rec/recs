import json
import os
import shutil
import subprocess as sp
import sys
import typing as t
from datetime import datetime
from multiprocessing import connection
from pathlib import Path

from threa import HasThread, Runnable, Runnables

from recs.base import RecsError, times
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.cfg import Aliases, Cfg, FileSource, InputDevice, Source, Track
from recs.cfg.device import DeviceDict, get_input_devices
from recs.daemon import gui_ipc

from . import gui_process, live
from .device_poller import DevicePoller
from .full_state import FullState
from .key_events import KeyEvent, make_key_recorder
from .session_manifest import (
    ManifestEvent,
    ManifestFile,
    ManifestFooter,
    ManifestWarning,
    SessionManifestWriter,
    timestamp_to_json,
)
from .source_process import SourceProcess
from .source_recorder import POLL_TIMEOUT, BufferStats, SourceFailure, SourceUpdate
from .source_tracks import input_device_tracks, source_tracks

FRAME_CLOCK_GRACE = 5.0
MIN_FRAME_CLOCK_RATIO = 0.5
SOURCE_STALL_TIMEOUT = 10.0
API_COMMANDS = [
    'calibrate',
    'capabilities',
    'disk_status',
    'list_devices',
    'mark',
    'pause_recording',
    'reload_profiles',
    'resume_recording',
    'set_key_label',
    'set_noise_floor',
    'shutdown',
    'start_recording',
    'status_snapshot',
    'stop_recording',
]


class Recorder(Runnables):
    def __init__(self, cfg: Cfg, *, display: bool = True) -> None:
        super().__init__()

        all_tracks = list(source_tracks(cfg))
        self.warnings: list[str] = []
        self.no_devices_reported = False
        self.no_channels_reported = False
        self.recording_paused = False
        self.recording_stopped = False
        self.state = FullState(all_tracks, cfg.aliases)
        self.cfg = _with_default_output_directory(cfg, self.state.start_time)
        if gui_ipc.daemon_mode_enabled():
            display_type = gui_ipc.DaemonGuiServer
        elif self.cfg.console.gui:
            display_type = gui_process.GuiProcess
        else:
            display_type = live.Live
        self.live = (
            display_type(self.rows, self.cfg, errors=self.error_messages)
            if display
            else None
        )
        self.sources = {
            source.name: SourceProcess(self.cfg, tracks)
            for source, tracks in all_tracks
        }
        self.frames = dict.fromkeys(self.sources, 0)
        self.buffer_stats: dict[str, BufferStats] = {}
        self.buffer_drops_reported = dict.fromkeys(self.sources, 0)
        self.source_frames_at_start = dict.fromkeys(self.sources, 0)
        self.source_start_times = dict.fromkeys(self.sources, self.state.start_time)
        self.source_last_updates = dict.fromkeys(self.sources, self.state.start_time)
        self.files_written: set[Path] = set()
        self.manifest_file_end_frames: dict[Path, int] = {}
        self.manifest_file_end_timestamps: dict[Path, float] = {}
        self.manifest_files: dict[Path, ManifestFile] = {}
        self.manifest: SessionManifestWriter | None = None
        self.key_recorder = make_key_recorder(cfg)
        self.disk_space_reported = False
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
        super().start()
        Runnable.start(self)

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
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
        return self.warnings.copy()

    def _record_startup_input_errors(
        self,
        all_tracks: t.Sequence[tuple[Source, t.Sequence[Track]]],
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
                self._receive_pending_updates()
                self._finish_manifest()
                if self.cfg.general.silence_preview:
                    print(json.dumps(self._silence_preview_report(), indent=2))
                elif self.cfg.general.calibrate or self.cfg.general.verbose:
                    print(json.dumps(self.state.db_ranges(), indent=2))
        self._summary()
        if self.cfg.console.open_output_folder:
            _open_folder(self._output_folder())

    def _summary(self) -> None:
        print(f'Recording time: {_summary_time(self.state.elapsed_time)}')
        files = sorted(path for path in self.files_written if path.exists())
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
        if self.files_written:
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
                    if self._disk_space_low():
                        break
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
                        self._receive_connection(t.cast(connection.Connection, c))
            finally:
                for source in self.hardware.values():
                    source.stop()
                for source in self.hardware.values():
                    source.join()

    def _done(self, sources: t.Sequence[SourceProcess]) -> bool:
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

    def _disk_space_low(self) -> bool:
        minimum = self.cfg.recording.minimum_free_space
        if not minimum:
            return False

        free = shutil.disk_usage(_existing_parent(self._manifest_path())).free
        if free >= minimum:
            return False

        if not self.disk_space_reported:
            warning = (
                f'Free disk space {free} bytes is below minimum_free_space={minimum}'
            )
            print(warning, file=sys.stderr)
            self._record_warning(warning)
            self.disk_space_reported = True
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
                    print(f'ERROR: {warning}', file=sys.stderr)
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
                    print(f'ERROR: {warning}', file=sys.stderr)
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
                self._add_source(source, tracks, aliases)

    def _add_source(
        self,
        source: InputDevice,
        tracks: t.Sequence[Track],
        aliases: Aliases,
    ) -> None:
        source_process = SourceProcess(self.cfg, tracks)
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
        print(f'ERROR: {warning}', file=sys.stderr)
        self._record_warning(warning)
        self.no_devices_reported = True

    def _report_no_channels(self) -> None:
        if self.no_channels_reported:
            return
        warning = 'No channels selected'
        print(f'ERROR: {warning}', file=sys.stderr)
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
            print(warning, file=sys.stderr)
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
        if self.live is None:
            return
        requests = t.cast(
            list[gui_ipc.ControlRequest], self.live.take_control_requests()
        )
        for request in requests:
            try:
                result = self._handle_control_request(request.command)
            except RecsError as e:
                request.reply(ok=False, message=str(e))
            else:
                request.reply(ok=True, result=result)

    def _handle_control_request(
        self,
        command: gui_ipc.Command,
    ) -> dict[str, object]:
        if command.command == 'calibrate':
            return self._calibrate_noise_floor()
        if command.command == 'capabilities':
            return {'commands': API_COMMANDS, 'version': gui_ipc.VERSION}
        if command.command == 'disk_status':
            return self._disk_status()
        if command.command == 'list_devices':
            return {'devices': self._device_status()}
        if command.command == 'mark':
            return self._mark(command)
        if command.command == 'pause_recording':
            return self._pause_recording('pause_recording')
        if command.command == 'reload_profiles':
            return self._reload_profiles()
        if command.command == 'resume_recording':
            return self._resume_recording('resume_recording')
        if command.command == 'set_key_label':
            return self._set_key_label(command)
        if command.command == 'set_noise_floor':
            return self._set_noise_floor(command)
        if command.command == 'start_recording':
            return self._resume_recording('start_recording')
        if command.command == 'status_snapshot':
            return self._status_snapshot()
        if command.command == 'stop_recording':
            return self._stop_recording()
        raise RecsError(f'Unsupported command: {command.command}')

    def _mark(self, command: gui_ipc.Command) -> dict[str, object]:
        if not command.label:
            raise RecsError('mark requires label')
        self._write_manifest_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='mark',
                label=command.label,
            )
        )
        return {'label': command.label}

    def _pause_recording(self, reason: str) -> dict[str, object]:
        self.recording_paused = True
        for source in self.hardware.values():
            if source.running:
                source.stop()
        self._write_manifest_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='recording_paused',
                label=reason,
            )
        )
        return self._recording_state()

    def _resume_recording(self, reason: str) -> dict[str, object]:
        self.recording_paused = False
        self.recording_stopped = False
        self._write_manifest_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='recording_resumed',
                label=reason,
            )
        )
        return self._recording_state()

    def _stop_recording(self) -> dict[str, object]:
        result = self._pause_recording('stop_recording')
        self.recording_stopped = True
        return result | self._recording_state()

    def _set_key_label(self, command: gui_ipc.Command) -> dict[str, object]:
        if not command.key:
            raise RecsError('set_key_label requires key')
        if not command.label:
            raise RecsError('set_key_label requires label')
        self.cfg.keys.labels[command.key] = command.label
        return {'key': command.key, 'label': command.label}

    def _set_noise_floor(self, command: gui_ipc.Command) -> dict[str, object]:
        if not command.source:
            raise RecsError('set_noise_floor requires source')
        if command.noise_floor is None:
            raise RecsError('set_noise_floor requires noise_floor')
        profiles_path = self.cfg.device.profiles
        if not profiles_path.name:
            raise RecsError('Cannot set noise floor without --profiles')
        profiles = self.cfg.device_profiles.copy()
        current = profiles.get(command.source, {})
        profiles[command.source] = current | {'noise_floor': command.noise_floor}
        _write_text_atomically(
            profiles_path,
            json.dumps(profiles, indent=2, sort_keys=True) + '\n',
        )
        self.cfg.__dict__.pop('device_profiles', None)
        for source in self.sources.values():
            source.cfg = self.cfg
        return {'source': command.source, 'noise_floor': command.noise_floor}

    def _reload_profiles(self) -> dict[str, object]:
        if not self.cfg.device.profiles.name:
            raise RecsError('Cannot reload profiles without --profiles')
        self.cfg.__dict__.pop('device_profiles', None)
        for source in self.sources.values():
            source.cfg = self.cfg
        return {'profiles_path': str(self.cfg.device.profiles)}

    def _status_snapshot(self) -> dict[str, object]:
        return {
            'disk': self._disk_status(),
            'devices': self._device_status(),
            'errors': self.error_messages(),
            'recording': self._recording_state(),
            'rows': list(self.rows()),
        }

    def _disk_status(self) -> dict[str, object]:
        path = _existing_parent(self._manifest_path()).resolve()
        usage = shutil.disk_usage(path)
        return {
            'free_bytes': usage.free,
            'path': str(path),
            'total_bytes': usage.total,
            'used_bytes': usage.used,
        }

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

    def _recording_state(self) -> dict[str, object]:
        return {
            'paused': self.recording_paused,
            'stopped': self.recording_stopped,
        }

    def _drain(self, conn: connection.Connection) -> None:
        while _connection_ready(conn):
            if not self._receive_connection(conn):
                break

    def _receive_connection(self, conn: connection.Connection) -> bool:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return False
        self._receive_source_message(t.cast(SourceUpdate | SourceFailure, msg))
        return True

    def _receive_source_message(self, message: SourceUpdate | SourceFailure) -> None:
        if isinstance(message, SourceFailure):
            warning = f'Device {message.source_name} failed: {message.message}'
            print(warning, file=sys.stderr)
            self._record_warning(warning)
            self.failed.add(message.source_name)
            return
        self._receive_update(message)

    def _receive_update(self, update: SourceUpdate) -> None:
        self.frames[update.source_name] += update.frames
        self._record_buffer_status(update)
        self.files_written.update(update.files)
        self.manifest_file_end_frames.update(update.file_end_frames or {})
        self.manifest_file_end_timestamps.update(update.file_end_timestamps or {})
        for file_record in update.file_records or []:
            record = ManifestFile(
                type='file_started',
                timestamp=timestamp_to_json(
                    _timestamp_or_now(file_record.start_timestamp)
                ),
                frame_count=file_record.start_frame,
                path=file_record.path.as_posix(),
                source=self._manifest_source(file_record.source_name),
                track=file_record.track,
                channels=file_record.channels,
                sample_rate=file_record.sample_rate,
                bit_depth=file_record.bit_depth,
            )
            self.manifest_files[file_record.path] = record
            self._write_manifest_record(record)
        source = self.sources[update.source_name]
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
                    ManifestEvent(
                        type='buffer_overflow',
                        timestamp=timestamp_to_json(
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
            print(warning, file=sys.stderr)
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
            print(warning, file=sys.stderr)
            self._record_warning(warning)
            self.lag_reported.add(source.name)
        return False

    def _record_track_activity(
        self,
        source_name: str,
        previous: dict[str, bool],
        updates: t.Mapping[str, t.Any],
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
    ) -> None:
        self._write_manifest_record(
            ManifestEvent(
                timestamp=timestamp_to_json(_timestamp_or_now(timestamp)),
                type=event_type,
                source=source,
                track=track,
                frame_count=frame_count,
                start_frame=start_frame,
            )
        )

    def _record_key_event(self, event: KeyEvent) -> None:
        self._write_manifest_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
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
        if self.cfg.general.dry_run or self.cfg.general.silence_preview:
            return
        self.manifest = SessionManifestWriter(
            self._manifest_path(),
            started_at=timestamp_to_json(self.state.start_time),
        )

    def _finish_manifest(self) -> None:
        if self.manifest is None:
            return
        for path, file in sorted(self.manifest_files.items()):
            if path.exists():
                self._write_manifest_record(
                    file.model_copy(
                        update={
                            'type': 'file_finished',
                            'timestamp': timestamp_to_json(
                                _timestamp_or_now(
                                    self.manifest_file_end_timestamps.get(path)
                                )
                            ),
                            'frame_count': self.manifest_file_end_frames.get(path),
                        }
                    )
                )
        self._write_manifest_record(
            ManifestFooter(
                ended_at=timestamp_to_json(times.timestamp()),
                duration=self.state.elapsed_time,
            )
        )
        self.manifest.close()

    def _record_warning(self, warning: str) -> None:
        self.warnings.append(warning)
        self._write_manifest_record(
            ManifestWarning(
                timestamp=timestamp_to_json(times.timestamp()),
                message=warning,
            )
        )

    def _write_manifest_record(
        self,
        record: ManifestEvent | ManifestFile | ManifestFooter | ManifestWarning,
    ) -> None:
        if self.manifest is not None:
            self.manifest.write(record)

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

    def _calibrate_noise_floor(self) -> dict[str, object]:
        profiles_path = self.cfg.device.profiles
        if not profiles_path.name:
            raise RecsError('Cannot calibrate noise floor without --profiles')

        report = self._silence_preview_report()
        profiles = self.cfg.device_profiles.copy()
        for source_name, profile in t.cast(
            dict[str, dict[str, object]], report['profiles']
        ).items():
            current = profiles.get(source_name, {})
            profiles[source_name] = current | profile

        _write_text_atomically(
            profiles_path,
            json.dumps(profiles, indent=2, sort_keys=True) + '\n',
        )
        self.cfg = type(self.cfg)(**self.cfg.model_dump())
        for source in self.sources.values():
            source.cfg = self.cfg
        return report | {'profiles_path': str(profiles_path)}

    def _manifest_path(self) -> Path:
        paths = sorted(path for path in self.files_written if path.exists())
        if paths:
            parent = Path(os.path.commonpath([path.parent for path in paths]))
            return parent / 'recs-session.jsonl'

        output_directory = self.cfg.directory.output_directory
        if output_directory:
            return _manifest_directory(output_directory, self.state.start_time) / (
                'recs-session.jsonl'
            )
        return Path('recs-session.jsonl')

    def _output_folder(self) -> Path:
        paths = sorted(path for path in self.files_written if path.exists())
        if paths:
            return Path(os.path.commonpath([path.parent for path in paths]))
        return _existing_parent(self._manifest_path()).resolve()


def _summary_time(seconds: float) -> str:
    value = times.to_str(seconds)
    if seconds < 60:
        return f'0:{value:0>6}'
    return value


def _with_default_output_directory(cfg: Cfg, timestamp: float) -> Cfg:
    if cfg.directory.output_directory:
        return cfg

    output_directory = _daemon_record_directory(cfg)
    if output_directory is None:
        output_directory = _available_session_directory(timestamp)

    directory = cfg.directory.model_copy(
        update={'output_directory': str(output_directory)}
    )
    result = cfg.model_copy(update={'directory': directory})
    result.__dict__.pop('output_path_pattern', None)
    return result


def _daemon_record_directory(cfg: Cfg) -> Path | None:
    if not gui_ipc.daemon_mode_enabled():
        return None
    path = Path(cfg.general.default_record_directory)
    if path.is_absolute():
        return path
    return _record_disk() / path


def _record_disk() -> Path:
    disks = _mounted_record_disks()
    if not disks:
        return Path.home()
    return max(disks, key=lambda p: shutil.disk_usage(p).free)


def _timestamp_or_now(timestamp: float | None) -> float:
    return times.timestamp() if timestamp is None else timestamp


def _mounted_record_disks() -> list[Path]:
    if os.name == 'nt':
        return _windows_record_disks()

    disks: list[Path] = []
    for parent in _record_disk_parents():
        try:
            children = list(parent.iterdir())
        except OSError:
            continue
        disks.extend(p for p in children if p.is_dir() and p.is_mount())
    return disks


def _record_disk_parents() -> list[Path]:
    parents = [Path('/Volumes'), Path('/media'), Path('/mnt')]
    user = os.environ.get('USER')
    if user:
        parents.append(Path('/run/media') / user)
    return parents


def _windows_record_disks() -> list[Path]:
    system = Path.home().anchor.lower()
    disks = []
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        path = Path(f'{letter}:/')
        if path.exists() and path.anchor.lower() != system:
            disks.append(path)
    return disks


def _available_session_directory(timestamp: float) -> Path:
    path = Path(_session_directory_name(timestamp))
    if not path.exists():
        return path

    index = 1
    while True:
        candidate = path.with_name(f'{path.name}_{index}')
        if not candidate.exists():
            return candidate
        index += 1


def _session_directory_name(timestamp: float) -> str:
    if os.name == 'nt':
        return datetime.fromtimestamp(timestamp).strftime('recs %Y-%m-%d %H-%M-%S')
    return datetime.fromtimestamp(timestamp).strftime('recs: %Y-%m-%d %H:%M:%S')


def _manifest_directory(output_directory: str, timestamp: float) -> Path:
    ts = datetime.fromtimestamp(timestamp)
    try:
        return Path(ts.strftime(output_directory).format(**_manifest_times(ts)))
    except KeyError:
        prefix = output_directory.split('{', 1)[0].rstrip('/\\')
        return Path(prefix or '.')


def _existing_parent(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path()


def _write_text_atomically(path: Path, content: str) -> None:
    tmp = path.with_name(f'.{path.name}.tmp')
    with tmp.open('w') as fp:
        fp.write(content)
        fp.flush()
        os.fsync(fp.fileno())
    tmp.replace(path)


def _open_folder(path: Path) -> None:
    commands = {
        'darwin': ['open', str(path)],
        'win32': ['explorer', str(path)],
    }
    command = commands.get(sys.platform, ['xdg-open', str(path)])
    sp.run(command, check=False)


def _manifest_times(ts: datetime) -> dict[str, str]:
    return {
        'date': ts.strftime('%Y%m%d'),
        'ddate': ts.strftime('%Y-%m-%d'),
        'dtime': ts.strftime('%H:%M:%S'),
        'hour': ts.strftime('%H'),
        'minute': ts.strftime('%M'),
        'month': ts.strftime('%m'),
        'sdate': ts.strftime('%Y-%m-%d'),
        'second': ts.strftime('%S'),
        'stime': ts.strftime('%H-%M-%S'),
        'time': ts.strftime('%H%M%S'),
        'timestamp': ts.isoformat(),
        'year': ts.strftime('%Y'),
    }


def _connection_ready(conn: connection.Connection) -> bool:
    try:
        return conn.poll()
    except OSError:
        return False
