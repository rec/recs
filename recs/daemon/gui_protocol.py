from typing import Literal

from pydantic import BaseModel, Field, TypeAdapter
from reccy import ipc

from recs.base.errors import ErrorRecord
from recs.cfg.track_names import DeviceTrackNames

VERSION = 3


class Hello(ipc.Hello):
    type: Literal['hello']
    role: Literal['daemon', 'gui']
    version: int = VERSION


class RowsMessage(BaseModel):
    type: Literal['rows']
    rows: list[dict[str, object]]
    errors: list[ErrorRecord] = Field(default_factory=list)


class KeyPressed(BaseModel):
    type: Literal['key_pressed']
    key: str


class KeyReleased(BaseModel):
    type: Literal['key_released']
    key: str


class Calibrate(BaseModel):
    type: Literal['calibrate']
    channels: dict[str, list[int]] = Field(default_factory=dict)


class Capabilities(BaseModel):
    type: Literal['capabilities']


class DiskStatusRequest(BaseModel):
    type: Literal['disk_status']


class GetCfg(BaseModel):
    type: Literal['get_cfg']
    address: str


class GetTrackNames(BaseModel):
    type: Literal['get_track_names']


class ListDevices(BaseModel):
    type: Literal['list_devices']


class MutableAttributes(BaseModel):
    type: Literal['mutable_attributes']


class Mark(BaseModel):
    type: Literal['mark']
    label: str


class PauseRecording(BaseModel):
    type: Literal['pause_recording']


class ReloadProfiles(BaseModel):
    type: Literal['reload_profiles']


class ResumeRecording(BaseModel):
    type: Literal['resume_recording']


class SetCfg(BaseModel):
    type: Literal['set_cfg']
    address: str
    value: object


class SetKeyLabel(BaseModel):
    type: Literal['set_key_label']
    key: str
    label: str


class SetNoiseFloor(BaseModel):
    type: Literal['set_noise_floor']
    source: str
    channel: int
    noise_floor: float | None


class ChannelTrack(BaseModel):
    channels: list[int]
    name: str = ''


class SetTrackNames(BaseModel):
    type: Literal['set_track_names']
    track_names: DeviceTrackNames


class SetTracks(BaseModel):
    type: Literal['set_tracks']
    source: str
    tracks: list[ChannelTrack]


class StartRecording(BaseModel):
    type: Literal['start_recording']


class StatusSnapshotRequest(BaseModel):
    type: Literal['status_snapshot']


class StopRecording(BaseModel):
    type: Literal['stop_recording']


class Calibrated(BaseModel):
    type: Literal['calibrated']
    measurements: dict[str, float]
    noise_floors: dict[str, dict[str, float]]


class CapabilitiesResult(BaseModel):
    type: Literal['capabilities_result']
    commands: list[str]
    version: int


class CfgSet(BaseModel):
    type: Literal['cfg_set']
    address: str
    value: object


class CfgValue(BaseModel):
    type: Literal['cfg_value']
    address: str
    value: object


class DiskStatus(BaseModel):
    type: Literal['disk_status_result']
    free_bytes: int
    path: str
    total_bytes: int
    used_bytes: int
    estimated_seconds_remaining: float | None = None
    alert_threshold: str | None = None
    alert_active: bool = False
    automatic_switch_armed: bool = False
    paused_for_disk_space: bool = False
    resume_disk: str | None = None


class Devices(BaseModel):
    type: Literal['devices']
    devices: list[dict[str, object]]


class KeyLabelSet(BaseModel):
    type: Literal['key_label_set']
    key: str
    label: str


class Marked(BaseModel):
    type: Literal['marked']
    label: str


class MutableAttributesResult(BaseModel):
    type: Literal['mutable_attributes_result']
    mutable_attributes: list[str]


class NoiseFloorSet(BaseModel):
    type: Literal['noise_floor_set']
    channel: int
    noise_floor: float | None
    source: str


class ProfilesReloaded(BaseModel):
    type: Literal['profiles_reloaded']
    profiles_path: str


class RecordingState(BaseModel):
    type: Literal['recording_state']
    paused: bool
    stopped: bool


class StatusSnapshot(BaseModel):
    type: Literal['status_snapshot_result']
    devices: list[dict[str, object]]
    disk: dict[str, object]
    errors: list[ErrorRecord]
    recording: dict[str, bool]
    rows: list[dict[str, object]]


class TrackNames(BaseModel):
    type: Literal['track_names']
    track_names: DeviceTrackNames


class TracksSet(BaseModel):
    type: Literal['tracks_set']
    source: str
    tracks: list[ChannelTrack]


class Shutdown(ipc.Shutdown):
    type: Literal['shutdown']


class Error(ipc.Error):
    type: Literal['error']
    message: str


Request = (
    Calibrate
    | Capabilities
    | DiskStatusRequest
    | GetCfg
    | GetTrackNames
    | ListDevices
    | MutableAttributes
    | Mark
    | PauseRecording
    | ReloadProfiles
    | ResumeRecording
    | SetCfg
    | SetKeyLabel
    | SetNoiseFloor
    | SetTrackNames
    | SetTracks
    | StartRecording
    | StatusSnapshotRequest
    | StopRecording
)

Response = (
    Calibrated
    | CapabilitiesResult
    | CfgSet
    | CfgValue
    | DiskStatus
    | Devices
    | KeyLabelSet
    | Marked
    | MutableAttributesResult
    | NoiseFloorSet
    | ProfilesReloaded
    | RecordingState
    | StatusSnapshot
    | TrackNames
    | TracksSet
    | Error
)

Message = Hello | RowsMessage | KeyPressed | KeyReleased | Request | Response | Shutdown

MESSAGE = TypeAdapter(Message)


def parse_message(line: str) -> Message:
    return MESSAGE.validate_json(line)
