from collections.abc import Callable
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from recs.base.errors import ErrorRecord
from recs.cfg import settings
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames
from recs.daemon import gui_protocol

from . import (
    disk_space,
    disk_space_policy,
    recording_commands,
    recording_control_protocol,
    recording_session,
    recording_track_config,
)
from .device_lifecycle import DeviceLifecycle
from .full_state import FullState
from .recording_control_protocol import RecordingControlTarget
from .session_manifest import ManifestRecord


class RecordingRuntimeState(BaseModel):
    recording_paused: bool = False
    shutdown_started: bool = False

    def resume(self) -> None:
        self.recording_paused = False


class RecordingControl:
    def __init__(
        self,
        cfg: Cfg,
        saved_tracks: dict[str, list[settings.TrackSettings]],
        track_names: SourceTrackNames,
        state: FullState,
        session: recording_session.RecordingSession,
        devices: DeviceLifecycle,
        disk: disk_space_policy.DiskSpacePolicy,
        write_record: Callable[[ManifestRecord], None],
        cfg_changed: Callable[[Cfg], None],
        rows: Callable[[], list[dict[str, object]]],
        error_records: Callable[[], list[ErrorRecord]],
        midi_status: Callable[[], list[dict[str, object]]],
        osc_status: Callable[[], list[dict[str, object]]],
        manifest_path: Callable[[], Path],
        receive_pending_updates: Callable[[], None],
        finish_manifest: Callable[[], None],
        card_replace: Callable[[], gui_protocol.CardReplaceStarted],
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
        self.midi_status = midi_status
        self.osc_status = osc_status
        self.manifest_path = manifest_path
        self.receive_pending_updates = receive_pending_updates
        self.finish_manifest = finish_manifest
        self.card_replace_callback = card_replace
        self.calibrate: Callable[[gui_protocol.Calibrate], gui_protocol.Calibrated]
        self.runtime_state = RecordingRuntimeState()
        self.cfg_revision = 0
        self.protocol = recording_control_protocol.RecordingControlProtocol(
            cast(RecordingControlTarget, self)
        )

    @property
    def recording_paused(self) -> bool:
        return self.runtime_state.recording_paused

    @recording_paused.setter
    def recording_paused(self, value: bool) -> None:
        self.runtime_state.recording_paused = value

    @property
    def shutdown_started(self) -> bool:
        return self.runtime_state.shutdown_started

    @shutdown_started.setter
    def shutdown_started(self, value: bool) -> None:
        self.runtime_state.shutdown_started = value

    def mark(self, request: gui_protocol.Mark) -> gui_protocol.Marked:
        return recording_commands.mark(self, request)

    def card_replace(self) -> gui_protocol.CardReplaceStarted:
        return self.card_replace_callback()

    def pause_recording(
        self, reason: str, disk: disk_space.Disk | None = None
    ) -> gui_protocol.RecordingState:
        return recording_commands.pause_recording(self, reason, disk)

    def resume_recording(
        self, reason: str, disk: disk_space.Disk | None = None
    ) -> gui_protocol.RecordingState:
        return recording_commands.resume_recording(self, reason, disk)

    def reload_profiles(self) -> gui_protocol.ProfilesReloaded:
        return recording_commands.reload_profiles(self)

    def status_snapshot(self) -> gui_protocol.StatusSnapshot:
        return recording_commands.status_snapshot(self)

    def disk_status(self) -> gui_protocol.DiskStatus:
        return recording_commands.disk_status(self)

    def device_status(self) -> list[dict[str, object]]:
        return recording_commands.device_status(self)

    def recording_state(self) -> gui_protocol.RecordingState:
        return recording_commands.recording_state(self)

    def set_waveforms_enabled(self, enabled: bool) -> None:
        self.devices.set_waveforms_enabled(enabled)

    def set_key_label(
        self, request: gui_protocol.SetKeyLabel
    ) -> gui_protocol.KeyLabelSet:
        return recording_track_config.set_key_label(self, request)

    def set_noise_floor(
        self, request: gui_protocol.SetNoiseFloor
    ) -> gui_protocol.NoiseFloorSet:
        return recording_track_config.set_noise_floor(self, request)

    def set_track_names(
        self, request: gui_protocol.SetTrackNames
    ) -> gui_protocol.TrackNames:
        return recording_track_config.set_track_names(self, request)

    def set_tracks(self, request: gui_protocol.SetTracks) -> gui_protocol.TracksSet:
        return recording_track_config.set_tracks(self, request)

    def get_cfg(self, request: gui_protocol.GetCfg) -> gui_protocol.CfgValue:
        return recording_track_config.get_cfg(self, request)

    def set_cfg(self, request: gui_protocol.SetCfg) -> gui_protocol.CfgSet:
        return recording_track_config.set_cfg(self, request)

    def set_cfg_value(
        self, address: str, value: object, *, save: bool = True
    ) -> object:
        return recording_track_config.set_cfg_value(self, address, value, save=save)

    def save_settings(self) -> None:
        recording_track_config.save_settings(self)

    def track_for_channel(self, source_name: str, channel: int) -> Track:
        return recording_track_config.track_for_channel(self, source_name, channel)
