from collections.abc import Callable, Mapping, Sequence
from multiprocessing import connection
from typing import cast

from recs.base import times
from recs.base.errors import RecsError
from recs.cfg import settings
from recs.cfg.aliases import Aliases
from recs.cfg.cfg import Cfg
from recs.cfg.device import DeviceDict, InputDevice, get_input_devices
from recs.cfg.file_source import FileSource
from recs.cfg.source import Source
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames

from .device_poller import DevicePoller
from .full_state import FullState
from .source_process import SourceProcess
from .source_recorder import BufferStats, SourceFailure, SourceUpdate
from .source_tracks import input_device_tracks, source_tracks

FRAME_CLOCK_GRACE = 5.0
MIN_FRAME_CLOCK_RATIO = 0.5
SOURCE_STALL_TIMEOUT = 10.0


class DeviceLifecycle:
    @staticmethod
    def initial_tracks(
        cfg: Cfg, saved_tracks: dict[str, list[settings.TrackSettings]]
    ) -> list[tuple[Source, Sequence[Track]]]:
        return [
            (source, _restored_tracks(source, tracks, saved_tracks))
            for source, tracks in source_tracks(cfg)
        ]

    def __init__(
        self,
        cfg: Cfg,
        state: FullState,
        saved_tracks: dict[str, list[settings.TrackSettings]],
        track_names: DeviceTrackNames,
        initial_tracks: list[tuple[Source, Sequence[Track]]],
        warning: Callable[[str], None],
        event: Callable[..., None],
        file_update: Callable[[SourceUpdate, SourceProcess], None],
        calibration_update: Callable[[str, dict[str, float]], None],
        buffer_update: Callable[[str, BufferStats], None],
        source_process: Callable[..., SourceProcess],
        device_poller: Callable[[float], DevicePoller],
    ) -> None:
        self.cfg = cfg
        self.state = state
        self.saved_tracks = saved_tracks
        self.track_names = track_names
        self.warning = warning
        self.event = event
        self.file_update = file_update
        self.calibration_update = calibration_update
        self.buffer_update = buffer_update
        self.source_process = source_process
        self.device_poller = device_poller
        self.source_processes = {
            source.key: self.source_process(cfg, tracks, track_names=track_names)
            for source, tracks in initial_tracks
        }
        self.hardware_sources = {
            name: source
            for name, source in self.source_processes.items()
            if isinstance(source.source, InputDevice)
        }
        self.file_sources = {
            name: source
            for name, source in self.source_processes.items()
            if isinstance(source.source, FileSource)
        }
        self.source_frames = dict.fromkeys(self.source_processes, 0)
        self.buffer_stats: dict[str, BufferStats] = {}
        self.buffer_drops_reported = dict.fromkeys(self.source_processes, 0)
        self.buffer_pressure_reported = dict.fromkeys(self.source_processes, 0.0)
        self.source_frames_at_start = dict.fromkeys(self.source_processes, 0)
        self.source_start_times = dict.fromkeys(self.source_processes, state.start_time)
        self.source_last_updates = dict.fromkeys(
            self.source_processes, state.start_time
        )
        self.failed_sources: set[str] = set()
        self.lag_reported: set[str] = set()
        self.present_hardware: set[str] = set()
        self.no_devices_reported = False
        self.no_channels_reported = False
        self.poller: DevicePoller | None = None
        if self.hardware_sources or not self.file_sources:
            self.poller = self.device_poller(cfg.console.sleep_time_device)
            self.poller.poll()

    @property
    def sources(self) -> dict[str, SourceProcess]:
        return self.source_processes

    @property
    def hardware(self) -> dict[str, SourceProcess]:
        return self.hardware_sources

    @property
    def files(self) -> dict[str, SourceProcess]:
        return self.file_sources

    @property
    def frames(self) -> dict[str, int]:
        return self.source_frames

    @property
    def failed(self) -> set[str]:
        return self.failed_sources

    @property
    def present(self) -> set[str]:
        return self.present_hardware

    def set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        self.cfg = cfg
        for source in self.source_processes.values():
            source.set_cfg(cfg, revision=revision)

    def set_track_names(self, track_names: DeviceTrackNames) -> None:
        self.track_names = track_names
        for source in self.source_processes.values():
            source.set_track_names(track_names)

    def poll(self, paused: bool, stopped: bool, expired: bool) -> None:
        if self.poller is None or (snapshot := self.poller.latest()) is None:
            return
        if snapshot:
            self.no_devices_reported = False
        elif not self.present_hardware:
            self._report_no_devices()
        self._add_detected_hardware(snapshot)
        compatible: set[str] = set()
        for name, source in self.hardware_sources.items():
            info = snapshot.get(name)
            if info is None:
                if name in self.present_hardware:
                    self.warning(f'Device {name} went offline')
                self.failed_sources.discard(name)
                source.stop()
                continue
            channels = int(info['max_input_channels'])
            if channels < source.required_channels:
                source.stop()
                if name not in self.failed_sources:
                    self.warning(
                        f'{name} has {channels} input channels; '
                        f'{source.required_channels} required'
                    )
                    self.failed_sources.add(name)
                continue
            compatible.add(name)
            if name not in self.present_hardware:
                self.failed_sources.discard(name)
            if (
                not source.started
                and name not in self.failed_sources
                and not paused
                and not stopped
                and not expired
            ):
                source.start()
                self.source_frames_at_start[name] = self.source_frames[name]
                self.source_start_times[name] = times.timestamp()
                self.source_last_updates[name] = self.source_start_times[name]
        self._record_presence(compatible)
        self.present_hardware = compatible
        if snapshot and not self.hardware_sources:
            self._report_no_channels()

    def reap(self) -> None:
        for name, source in self.source_processes.items():
            if not source.started or source.is_alive:
                continue
            self._drain(source.connection)
            expected = not source.running
            source.join(timeout=0)
            for update in source.take_updates():
                self.receive_message(update)
            if (
                name in self.hardware_sources
                and not expected
                and name in self.present_hardware
            ):
                self.failed_sources.add(name)

    def stop_stalled(self) -> None:
        now = times.timestamp()
        for name, source in self.source_processes.items():
            if not source.started or not source.is_alive or not source.running:
                continue
            if now - self.source_last_updates[name] <= SOURCE_STALL_TIMEOUT:
                continue
            self.warning(f'Device {name} stopped sending updates')
            source.stop()
            source.join()
            if name in self.hardware_sources:
                self.failed_sources.add(name)

    def receive_pending_updates(self) -> None:
        for source in self.source_processes.values():
            for update in source.take_updates():
                self.receive_message(update)

    def receive_connection(self, conn: connection.Connection) -> bool:
        try:
            message = conn.recv()
        except (EOFError, OSError):
            return False
        self.receive_message(cast(SourceUpdate | SourceFailure, message))
        return True

    def receive_message(self, message: SourceUpdate | SourceFailure) -> None:
        if isinstance(message, SourceFailure):
            self.warning(f'Device {message.source_name} failed: {message.message}')
            self.failed_sources.add(message.source_name)
            return
        self._receive_update(message)

    def stop_hardware(self) -> None:
        for source in self.hardware_sources.values():
            source.stop()

    def join_hardware(self) -> None:
        for source in self.hardware_sources.values():
            source.join()

    def _receive_update(self, update: SourceUpdate) -> None:
        self.source_frames[update.source_name] += update.frames
        self._record_buffer_status(update)
        source = self.source_processes[update.source_name]
        self.file_update(update, source)
        previous = {
            track_name: channel_state.is_active
            for track_name, channel_state in self.state.state[
                update.source_name
            ].items()
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
            self.calibration_update(update.source_name, update.calibration)
        for revision in update.config_revisions_applied or []:
            self.event('cfg_applied', source=update.source_name, value=revision)
        if source.running and not self._frame_clock_valid(source, now):
            source.stop()
            self.failed_sources.add(update.source_name)
        elif source.running and self._source_time_expired(source):
            source.stop()

    def _add_detected_hardware(self, snapshot: dict[str, DeviceDict]) -> None:
        if self.cfg.device.devices.name:
            return
        devices = get_input_devices(list(snapshot.values()))
        aliases = Aliases(self.cfg.device.alias, devices)
        for source, tracks in input_device_tracks(self.cfg, devices):
            if source.key in self.source_processes:
                continue
            tracks = _restored_tracks(source, tracks, self.saved_tracks)
            self._add_source(source, tracks, aliases)

    def _add_source(
        self, source: InputDevice, tracks: Sequence[Track], aliases: Aliases
    ) -> None:
        process = self.source_process(self.cfg, tracks, track_names=self.track_names)
        self.source_processes[source.key] = process
        self.hardware_sources[source.key] = process
        self.source_frames[source.key] = 0
        self.buffer_drops_reported[source.key] = 0
        self.buffer_pressure_reported[source.key] = 0.0
        self.source_frames_at_start[source.key] = 0
        self.source_start_times[source.key] = self.state.start_time
        self.source_last_updates[source.key] = self.state.start_time
        self.state.add_source(source, tracks, aliases)
        self.no_channels_reported = False

    def _report_no_devices(self) -> None:
        if not self.no_devices_reported:
            self.warning('No input devices detected')
            self.no_devices_reported = True

    def _report_no_channels(self) -> None:
        if not self.no_channels_reported:
            self.warning('No channels selected')
            self.no_channels_reported = True

    def _record_presence(self, compatible: set[str]) -> None:
        for name in sorted(compatible - self.present_hardware):
            self.event(
                'source_online',
                source=name,
                start_frame=self.source_frames_at_start[name],
            )
        for name in sorted(self.present_hardware - compatible):
            for track_name, channel_state in self.state.state[name].items():
                if channel_state.is_active:
                    self.event('track_stopped', source=name, track=track_name)
            self.event('source_offline', source=name)

    def _record_buffer_status(self, update: SourceUpdate) -> None:
        if update.buffer_stats is not None:
            self.buffer_stats[update.source_name] = update.buffer_stats
            reported = self.buffer_drops_reported[update.source_name]
            if update.buffer_stats.dropped_frames > reported:
                self.buffer_update(update.source_name, update.buffer_stats)
                self.buffer_drops_reported[
                    update.source_name
                ] = update.buffer_stats.dropped_frames
            pressure = self.buffer_pressure_reported[update.source_name]
            threshold = self.cfg.recording.audio_buffer_seconds * 0.8
            if (
                update.buffer_stats.max_queued_seconds > pressure
                and update.buffer_stats.max_queued_seconds >= threshold
            ):
                self.buffer_update(update.source_name, update.buffer_stats)
                self.buffer_pressure_reported[
                    update.source_name
                ] = update.buffer_stats.max_queued_seconds
        for warning in update.buffer_warnings or []:
            self.warning(warning)

    def _frame_clock_valid(self, source: SourceProcess, now: float) -> bool:
        if source.name not in self.hardware_sources:
            return True
        elapsed = now - self.source_start_times[source.name]
        if elapsed < FRAME_CLOCK_GRACE:
            return True
        frames = (
            self.source_frames[source.name] - self.source_frames_at_start[source.name]
        )
        recorded = frames / source.source.samplerate
        if recorded >= elapsed * MIN_FRAME_CLOCK_RATIO:
            return True
        if source.name not in self.lag_reported:
            self.warning(f'Device {source.source.name} lagging behind real time')
            self.lag_reported.add(source.name)
        return False

    def _source_time_expired(self, source: SourceProcess) -> bool:
        total = self.cfg.recording.total_run_time
        return bool(
            total
            and self.source_frames[source.name]
            >= round(total * source.source.samplerate)
        )

    def _record_track_activity(
        self,
        source: str,
        previous: dict[str, bool],
        updates: Mapping[str, object],
        frame_count: int | None,
        timestamp: float | None,
    ) -> None:
        for track_name in updates:
            active = self.state.state[source][track_name].is_active
            if active != previous[track_name]:
                self.event(
                    'track_started' if active else 'track_stopped',
                    source=source,
                    track=track_name,
                    frame_count=frame_count,
                    timestamp=timestamp,
                )

    def _drain(self, conn: connection.Connection) -> None:
        while conn.poll():
            if not self.receive_connection(conn):
                return


def _restored_tracks(
    source: Source,
    defaults: Sequence[Track],
    saved_tracks: dict[str, list[settings.TrackSettings]],
) -> Sequence[Track]:
    saved = saved_tracks.get(source.key)
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
