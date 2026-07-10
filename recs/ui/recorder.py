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
from recs.cfg import Cfg, FileSource, InputDevice
from recs.daemon import gui_ipc

from . import gui_process, live
from .device_poller import DevicePoller
from .full_state import FullState
from .key_events import KeyEvent, make_key_recorder
from .session_manifest import (
    ManifestEvent,
    ManifestFile,
    SessionManifest,
    timestamp_to_json,
)
from .source_process import SourceProcess
from .source_recorder import POLL_TIMEOUT, SourceFailure, SourceUpdate
from .source_tracks import source_tracks

FRAME_CLOCK_GRACE = 5.0
MIN_FRAME_CLOCK_RATIO = 0.5
SOURCE_STALL_TIMEOUT = 10.0


class Recorder(Runnables):
    def __init__(self, cfg: Cfg, *, display: bool = True) -> None:
        super().__init__()

        if not (all_tracks := list(source_tracks(cfg))):
            raise RecsError('No channels selected')

        self.state = FullState(all_tracks, cfg.aliases)
        self.cfg = _with_default_output_directory(cfg, self.state.start_time)
        if gui_ipc.daemon_mode_enabled():
            display_type = gui_ipc.DaemonGuiServer
        elif self.cfg.console.gui:
            display_type = gui_process.GuiProcess
        else:
            display_type = live.Live
        self.live = display_type(self.rows, self.cfg) if display else None
        self.sources = {
            source.name: SourceProcess(self.cfg, tracks)
            for source, tracks in all_tracks
        }
        self.frames = dict.fromkeys(self.sources, 0)
        self.source_frames_at_start = dict.fromkeys(self.sources, 0)
        self.source_start_times = dict.fromkeys(self.sources, self.state.start_time)
        self.source_last_updates = dict.fromkeys(self.sources, self.state.start_time)
        self.files_written: set[Path] = set()
        self.manifest_events: list[ManifestEvent] = []
        self.manifest_files: dict[Path, ManifestFile] = {}
        self.key_recorder = make_key_recorder(cfg)
        self.warnings: list[str] = []
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
        if self.hardware:
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

    def start(self) -> None:
        super().start()
        Runnable.start(self)

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        return self.state.rows()

    def run(self) -> None:
        with raise_keyboard_interrupt_on_signal():
            try:
                self._run()
            except KeyboardInterrupt:
                print('Interrupted', file=sys.stderr)
            finally:
                self._receive_pending_updates()
                self._write_manifest()
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
                f'Free disk space {free} bytes is below '
                f'minimum_free_space={minimum}'
            )
            print(warning, file=sys.stderr)
            self.warnings.append(warning)
            self.disk_space_reported = True
        return True

    def _poll_devices(self) -> None:
        if self.poller is None or (snapshot := self.poller.latest()) is None:
            return

        compatible: set[str] = set()
        for name, source in self.hardware.items():
            info = snapshot.get(name)
            if info is None:
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
                    self.warnings.append(warning)
                    self.failed.add(name)
                continue

            compatible.add(name)
            if name not in self.present:
                self.failed.discard(name)
            if (
                not source.started
                and name not in self.failed
                and not self._invocation_expired()
            ):
                source.start()
                self.source_frames_at_start[name] = self.frames[name]
                self.source_start_times[name] = times.timestamp()
                self.source_last_updates[name] = self.source_start_times[name]

        self._record_source_presence(compatible)
        self.present = compatible

    def _record_source_presence(self, compatible: set[str]) -> None:
        for name in sorted(compatible - self.present):
            self._record_event('source_online', source=name)
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
            self.warnings.append(warning)
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
            self.warnings.append(warning)
            self.failed.add(message.source_name)
            return
        self._receive_update(message)

    def _receive_update(self, update: SourceUpdate) -> None:
        self.frames[update.source_name] += update.frames
        self.files_written.update(update.files)
        for file_record in update.file_records or []:
            self.manifest_files[file_record.path] = ManifestFile(
                path=file_record.path.as_posix(),
                source=self._manifest_source(file_record.source_name),
                track=file_record.track,
                channels=file_record.channels,
                sample_rate=file_record.sample_rate,
                bit_depth=file_record.bit_depth,
            )
        source = self.sources[update.source_name]
        previous = {
            track_name: state.is_active
            for track_name, state in self.state.state[update.source_name].items()
        }
        self.state.update({update.source_name: update.channels})
        self._record_track_activity(update.source_name, previous, update.channels)
        now = times.timestamp()
        self.source_last_updates[update.source_name] = now
        if source.running and not self._source_frame_clock_valid(source, now):
            source.stop()
            self.failed.add(update.source_name)
            return
        if source.running and self._source_time_expired(source):
            source.stop()

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
            self.warnings.append(warning)
            self.lag_reported.add(source.name)
        return False

    def _record_track_activity(
        self,
        source_name: str,
        previous: dict[str, bool],
        updates: t.Mapping[str, t.Any],
    ) -> None:
        for track_name in updates:
            active = self.state.state[source_name][track_name].is_active
            was_active = previous[track_name]
            if active == was_active:
                continue
            event_type = 'track_started' if active else 'track_stopped'
            self._record_event(event_type, source=source_name, track=track_name)

    def _record_event(
        self,
        event_type: str,
        *,
        source: str,
        track: str | None = None,
    ) -> None:
        self.manifest_events.append(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type=event_type,
                source=source,
                track=track,
            )
        )

    def _record_key_event(self, event: KeyEvent) -> None:
        self.manifest_events.append(
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

    def _write_manifest(self) -> None:
        if self.cfg.general.dry_run or self.cfg.general.silence_preview:
            return
        files = [
            file for path, file in sorted(self.manifest_files.items()) if path.exists()
        ]
        manifest = SessionManifest(
            started_at=timestamp_to_json(self.state.start_time),
            ended_at=timestamp_to_json(times.timestamp()),
            duration=self.state.elapsed_time,
            events=self.manifest_events,
            files=files,
            warnings=self.warnings,
        )
        manifest.write(self._manifest_path())

    def _manifest_source(self, source_name: str) -> str | None:
        if isinstance(self.sources[source_name].source, FileSource):
            return source_name
        return None

    def _silence_preview_report(self) -> dict[str, object]:
        measurements = self.state.db_ranges()
        noise_floor = max(measurements.values(), default=0.0) + 6.0
        return {
            'measurements': measurements,
            'recommendations': {
                'noise_floor': round(noise_floor, 1),
                'quiet_before_start': self.cfg.recording.quiet_before_start,
                'quiet_after_end': self.cfg.recording.quiet_after_end,
            },
            'flags': {
                'noise_floor': f'--noise-floor {noise_floor:.1f}',
                'quiet_before_start': (
                    f'--quiet-before-start '
                    f'{self.cfg.recording.quiet_before_start:g}'
                ),
                'quiet_after_end': (
                    f'--quiet-after-end {self.cfg.recording.quiet_after_end:g}'
                ),
            },
        }

    def _manifest_path(self) -> Path:
        paths = sorted(path for path in self.files_written if path.exists())
        if paths:
            parent = Path(os.path.commonpath([path.parent for path in paths]))
            return parent / 'recs-session.json'

        output_directory = self.cfg.directory.output_directory
        if output_directory:
            return _manifest_directory(output_directory, self.state.start_time) / (
                'recs-session.json'
            )
        return Path('recs-session.json')

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

    directory = cfg.directory.model_copy(
        update={'output_directory': str(_available_session_directory(timestamp))}
    )
    result = cfg.model_copy(update={'directory': directory})
    result.__dict__.pop('output_path_pattern', None)
    return result


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
