import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from recs.base import times
from recs.base.errors import ErrorRecord, RecsError
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames, validate_track_names
from recs.daemon import external_ipc, gui_ipc, gui_protocol

from . import disk_monitor, disk_space, recording_paths, recording_session
from .device_lifecycle import DeviceLifecycle
from .full_state import FullState
from .session_manifest import ManifestEvent, ManifestRecord, timestamp_to_json
from .source_process import SourceProcess

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


class ControlDisplay(Protocol):
    def take_control_requests(self) -> list[gui_ipc.ControlRequest]:
        ...


class RecordingControl:
    def __init__(
        self,
        cfg: Cfg,
        saved_tracks: dict[str, list[settings.TrackSettings]],
        track_names: DeviceTrackNames,
        state: FullState,
        session: recording_session.RecordingSession,
        devices: DeviceLifecycle,
        disk: disk_monitor.DiskMonitor,
        write_record: Callable[[ManifestRecord], None],
        cfg_changed: Callable[[Cfg], None],
        rows: Callable[[], list[dict[str, object]]],
        error_records: Callable[[], list[ErrorRecord]],
        manifest_path: Callable[[], Path],
        receive_pending_updates: Callable[[], None],
        finish_manifest: Callable[[], None],
        start_recording_session: Callable[[], None],
    ) -> None:
        self.cfg = cfg
        self.saved_tracks = saved_tracks
        self.track_names = track_names
        self.state = state
        self.session = session
        self.devices = devices
        self.disk = disk
        self.write_record = write_record
        self.cfg_changed = cfg_changed
        self.rows = rows
        self.error_records = error_records
        self.manifest_path = manifest_path
        self.receive_pending_updates = receive_pending_updates
        self.finish_manifest = finish_manifest
        self.start_recording_session = start_recording_session
        self.calibrate: Callable[[gui_protocol.Calibrate], gui_protocol.Calibrated]
        self.recording_paused = False
        self.recording_stopped = False
        self.session_stopped = False
        self.shutdown_started = False

    @property
    def sources(self) -> dict[str, SourceProcess]:
        return self.devices.sources

    @property
    def hardware(self) -> dict[str, SourceProcess]:
        return self.devices.hardware

    def receive(
        self,
        live: ControlDisplay | None,
        external: external_ipc.ExternalServer | None,
        warning: Callable[[str], None],
        shutdown: Callable[[], None],
    ) -> None:
        if isinstance(live, gui_ipc.DaemonGuiServer):
            for error in live.take_protocol_errors():
                warning(f'Malformed GUI protocol message: {error}')
        requests = live.take_control_requests() if live is not None else []
        for request in requests:
            try:
                response = self.handle(request.request)
            except RecsError as error:
                response = gui_protocol.Error(type='error', message=str(error))
            request.respond(response)
        if external is None:
            return
        for request in external.take_requests():
            try:
                parsed = external_ipc.recs_request(request.request)
                if isinstance(parsed, gui_protocol.Shutdown):
                    if not self.shutdown_started:
                        self.shutdown_started = True
                        shutdown()
                    response = gui_protocol.RecordingState(
                        type='recording_state', paused=False, stopped=True
                    )
                else:
                    response = self.handle(parsed)
            except (RecsError, ValidationError) as error:
                warning(f'External Recs protocol error: {error}')
                response = gui_protocol.Error(type='error', message=str(error))
            external.respond(request, external_ipc.response(request.request, response))

    def publish(
        self,
        external: external_ipc.ExternalServer | None,
        rows: list[dict[str, object]],
        errors: list[ErrorRecord],
    ) -> None:
        if external is not None:
            external.publish_rows(rows, errors)

    def handle(self, request: gui_protocol.Request) -> gui_protocol.Response:
        if isinstance(request, gui_protocol.Calibrate):
            return self.calibrate(request)
        if isinstance(request, gui_protocol.Capabilities):
            return gui_protocol.CapabilitiesResult(
                type='capabilities_result',
                commands=API_COMMANDS,
                version=gui_protocol.VERSION,
            )
        if isinstance(request, gui_protocol.DiskStatusRequest):
            return self.disk_status()
        if isinstance(request, gui_protocol.GetCfg):
            return self.get_cfg(request)
        if isinstance(request, gui_protocol.GetTrackNames):
            return gui_protocol.TrackNames(
                type='track_names', track_names=self.track_names
            )
        if isinstance(request, gui_protocol.ListDevices):
            return gui_protocol.Devices(type='devices', devices=self.device_status())
        if isinstance(request, gui_protocol.MutableAttributes):
            return gui_protocol.MutableAttributesResult(
                type='mutable_attributes_result',
                mutable_attributes=sorted(self.cfg.mutable_attributes),
            )
        if isinstance(request, gui_protocol.Mark):
            return self.mark(request)
        if isinstance(request, gui_protocol.PauseRecording):
            return self.pause_recording('pause_recording')
        if isinstance(request, gui_protocol.ReloadProfiles):
            return self.reload_profiles()
        if isinstance(request, gui_protocol.ResumeRecording):
            return self.resume_recording('resume_recording')
        if isinstance(request, gui_protocol.SetCfg):
            return self.set_cfg(request)
        if isinstance(request, gui_protocol.SetKeyLabel):
            return self.set_key_label(request)
        if isinstance(request, gui_protocol.SetNoiseFloor):
            return self.set_noise_floor(request)
        if isinstance(request, gui_protocol.SetTrackNames):
            return self.set_track_names(request)
        if isinstance(request, gui_protocol.SetTracks):
            return self.set_tracks(request)
        if isinstance(request, gui_protocol.StartRecording):
            return self.resume_recording('start_recording')
        if isinstance(request, gui_protocol.StatusSnapshotRequest):
            return self.status_snapshot()
        if isinstance(request, gui_protocol.StopRecording):
            return self.stop_recording()
        raise RecsError(f'Unsupported request: {request.type}')

    def mark(self, request: gui_protocol.Mark) -> gui_protocol.Marked:
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='mark',
                label=request.label,
            )
        )
        return gui_protocol.Marked(type='marked', label=request.label)

    def pause_recording(
        self, reason: str, disk: disk_space.Disk | None = None
    ) -> gui_protocol.RecordingState:
        self.recording_paused = True
        for source in self.hardware.values():
            if source.running:
                source.stop()
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='recording_paused',
                label=reason,
                reason=reason,
                current_path=str(self.cfg.directory.output_directory),
                free_bytes=disk.free_bytes if disk else None,
            )
        )
        return self.recording_state()

    def resume_recording(
        self, reason: str, disk: disk_space.Disk | None = None
    ) -> gui_protocol.RecordingState:
        if self.session_stopped:
            self.start_recording_session()
        self.recording_paused = False
        self.recording_stopped = False
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='recording_resumed',
                label=reason,
                reason=reason,
                path=str(self.cfg.directory.output_directory),
                free_bytes=disk.free_bytes if disk else None,
            )
        )
        return self.recording_state()

    def stop_recording(self) -> gui_protocol.RecordingState:
        if self.recording_stopped:
            return self.recording_state()
        self.pause_recording('stop_recording')
        self.recording_stopped = True
        self.session_stopped = self.session.manifest is not None
        if self.session_stopped:
            for source in self.hardware.values():
                source.join()
            self.receive_pending_updates()
            self.finish_manifest()
        return self.recording_state()

    def set_key_label(
        self, request: gui_protocol.SetKeyLabel
    ) -> gui_protocol.KeyLabelSet:
        labels = self.cfg.keys.labels | {request.key: request.label}
        self.set_cfg_value(
            'keys.key_label', [f'{key}={label}' for key, label in labels.items()]
        )
        return gui_protocol.KeyLabelSet(
            type='key_label_set', key=request.key, label=request.label
        )

    def set_noise_floor(
        self, request: gui_protocol.SetNoiseFloor
    ) -> gui_protocol.NoiseFloorSet:
        track = self.track_for_channel(request.source, request.channel)
        floors = {
            source: dict(channels)
            for source, channels in self.cfg.recording.channel_noise_floors.items()
        }
        floors.setdefault(request.source, {})[track.name] = request.noise_floor
        self.set_cfg_value('recording.channel_noise_floors', floors)
        return gui_protocol.NoiseFloorSet(
            type='noise_floor_set',
            source=request.source,
            channel=request.channel,
            noise_floor=request.noise_floor,
        )

    def set_track_names(
        self, request: gui_protocol.SetTrackNames
    ) -> gui_protocol.TrackNames:
        try:
            track_names = validate_track_names(request.track_names)
        except ValueError as e:
            raise RecsError(str(e)) from None
        self.track_names = {
            device: dict(names) for device, names in track_names.items()
        }
        self.devices.set_track_names(self.track_names)
        self.state.set_track_names(self.track_names)
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='track_names_set',
                value=self.track_names,
            )
        )
        self.save_settings()
        return gui_protocol.TrackNames(type='track_names', track_names=self.track_names)

    def set_tracks(self, request: gui_protocol.SetTracks) -> gui_protocol.TracksSet:
        source = self.hardware.get(request.source)
        if source is None:
            raise RecsError(f'Unknown input device: {request.source}')
        tracks = self.updated_tracks(source, request.tracks)
        names = self.updated_track_names(request.source, request.tracks)
        floors = self.updated_track_noise_floors(source, request.tracks)
        if floors != self.cfg.recording.channel_noise_floors:
            self.set_cfg_value('recording.channel_noise_floors', floors, save=False)
        self.track_names = names
        source.set_tracks(tracks, names)
        self.saved_tracks[source.name] = [
            settings.TrackSettings(channels=list(track.channels)) for track in tracks
        ]
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='tracks_set',
                source=request.source,
                value=[track.model_dump() for track in request.tracks],
            )
        )
        self.save_settings()
        return gui_protocol.TracksSet(
            type='tracks_set', source=request.source, tracks=request.tracks
        )

    def updated_tracks(
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

    def updated_track_names(
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

    def updated_track_noise_floors(
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
                if set(track_channels(track)) & set(definition.channels)
            ]
            if len(set(matching)) > 1:
                raise RecsError(
                    'Cannot pair channels with different noise floors: '
                    f'{definition.channels}'
                )
            if matching:
                device_floors[track_name(definition.channels)] = matching[0]
        if not device_floors:
            del floors[source.name]
        return floors

    def get_cfg(self, request: gui_protocol.GetCfg) -> gui_protocol.CfgValue:
        try:
            value = self.cfg.get_attr(request.address)
        except ValueError as e:
            raise RecsError(str(e)) from None
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='cfg_get',
                address=request.address,
                value=value,
            )
        )
        return gui_protocol.CfgValue(
            type='cfg_value', address=request.address, value=value
        )

    def set_cfg(self, request: gui_protocol.SetCfg) -> gui_protocol.CfgSet:
        value = self.set_cfg_value(request.address, request.value)
        return gui_protocol.CfgSet(type='cfg_set', address=request.address, value=value)

    def set_cfg_value(
        self, address: str, value: object, *, save: bool = True
    ) -> object:
        try:
            self.cfg = self.cfg.set_attr(address, value)
        except ValueError as e:
            raise RecsError(str(e)) from None
        value = self.cfg.get_attr(address)
        self.devices.set_cfg(self.cfg)
        self.cfg_changed(self.cfg)
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(times.timestamp()),
                type='cfg_set',
                address=address,
                value=value,
            )
        )
        if save:
            self.save_settings()
        return value

    def save_settings(self) -> None:
        if self.cfg.save_settings:
            settings.save(self.cfg, self.track_names, self.saved_tracks)

    def reload_profiles(self) -> gui_protocol.ProfilesReloaded:
        if not self.cfg.device.profiles.name:
            raise RecsError('Cannot reload profiles without --profiles')
        self.cfg.__dict__.pop('device_profiles', None)
        for source in self.sources.values():
            source.cfg = self.cfg
        return gui_protocol.ProfilesReloaded(
            type='profiles_reloaded', profiles_path=str(self.cfg.device.profiles)
        )

    def status_snapshot(self) -> gui_protocol.StatusSnapshot:
        return gui_protocol.StatusSnapshot(
            type='status_snapshot_result',
            disk=self.disk_status().model_dump(exclude={'type'}),
            devices=self.device_status(),
            errors=self.error_records(),
            recording=self.recording_state().model_dump(exclude={'type'}),
            rows=self.rows(),
        )

    def disk_status(self) -> gui_protocol.DiskStatus:
        path = recording_paths.existing_parent(self.manifest_path()).resolve()
        usage = shutil.disk_usage(path)
        resume_disk = next(
            (
                disk.path
                for disk in self.disk.removable_disks()
                if disk.free_bytes >= self.disk.emergency_threshold(disk)
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
                usage.free / self.disk.rate.bytes_per_second
                if self.disk.rate.bytes_per_second
                else None
            ),
            alert_threshold=self.disk.alert_threshold,
            alert_active=self.disk.first_alert,
            automatic_switch_armed=(
                self.disk.first_alert and self.cfg.recording.disk_auto_switch
            ),
            paused_for_disk_space=self.disk.paused,
            resume_disk=str(resume_disk) if resume_disk else None,
        )

    def device_status(self) -> list[dict[str, object]]:
        devices: list[dict[str, object]] = []
        for name, source in sorted(self.sources.items()):
            device = source.source
            devices.append(
                {
                    'channels': device.channels,
                    'name': name,
                    'online': name in self.devices.present,
                    'sample_rate': device.samplerate,
                }
            )
        return devices

    def recording_state(self) -> gui_protocol.RecordingState:
        return gui_protocol.RecordingState(
            type='recording_state',
            paused=self.recording_paused,
            stopped=self.recording_stopped,
        )

    def track_for_channel(self, source_name: str, channel: int) -> Track:
        source = self.hardware.get(source_name)
        if source is None:
            raise RecsError(f'Unknown input device: {source_name}')
        if channel <= 0:
            raise RecsError('Channel must be positive')
        for track in source.tracks:
            if channel in track.channels:
                return track
        raise RecsError(f'Device {source_name} has no selected channel {channel}')


def track_channels(track_name: str) -> list[int]:
    return [int(channel) for channel in track_name.split('-') if channel]


def track_name(channels: list[int]) -> str:
    return '-'.join(str(channel) for channel in channels)
