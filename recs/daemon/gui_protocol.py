import typing

from pydantic import BaseModel, Field, TypeAdapter
from reccy import ipc

from recs.cfg.track_names import DeviceTrackNames

VERSION = 2


class Hello(ipc.Hello):
    type: typing.Literal['hello']
    role: typing.Literal['daemon', 'gui']
    version: int = VERSION


class RowsMessage(BaseModel):
    type: typing.Literal['rows']
    rows: list[dict[str, object]]
    errors: list[str] = Field(default_factory=list)


class KeyPressed(BaseModel):
    type: typing.Literal['key_pressed']
    key: str


class KeyReleased(BaseModel):
    type: typing.Literal['key_released']
    key: str


class Calibrate(BaseModel):
    type: typing.Literal['calibrate']
    channels: dict[str, list[int]] = Field(default_factory=dict)


class Capabilities(BaseModel):
    type: typing.Literal['capabilities']


class DiskStatusRequest(BaseModel):
    type: typing.Literal['disk_status']


class GetCfg(BaseModel):
    type: typing.Literal['get_cfg']
    address: str


class GetTrackNames(BaseModel):
    type: typing.Literal['get_track_names']


class ListDevices(BaseModel):
    type: typing.Literal['list_devices']


class MutableAttributes(BaseModel):
    type: typing.Literal['mutable_attributes']


class Mark(BaseModel):
    type: typing.Literal['mark']
    label: str


class PauseRecording(BaseModel):
    type: typing.Literal['pause_recording']


class ReloadProfiles(BaseModel):
    type: typing.Literal['reload_profiles']


class ResumeRecording(BaseModel):
    type: typing.Literal['resume_recording']


class SetCfg(BaseModel):
    type: typing.Literal['set_cfg']
    address: str
    value: object


class SetKeyLabel(BaseModel):
    type: typing.Literal['set_key_label']
    key: str
    label: str


class SetNoiseFloor(BaseModel):
    type: typing.Literal['set_noise_floor']
    source: str
    channel: int
    noise_floor: float | None


class SetTrackNames(BaseModel):
    type: typing.Literal['set_track_names']
    track_names: DeviceTrackNames


class StartRecording(BaseModel):
    type: typing.Literal['start_recording']


class StatusSnapshotRequest(BaseModel):
    type: typing.Literal['status_snapshot']


class StopRecording(BaseModel):
    type: typing.Literal['stop_recording']


class Calibrated(BaseModel):
    type: typing.Literal['calibrated']
    measurements: dict[str, float]
    noise_floors: dict[str, dict[str, float]]


class CapabilitiesResult(BaseModel):
    type: typing.Literal['capabilities_result']
    commands: list[str]
    version: int


class CfgSet(BaseModel):
    type: typing.Literal['cfg_set']
    address: str
    value: object


class CfgValue(BaseModel):
    type: typing.Literal['cfg_value']
    address: str
    value: object


class DiskStatus(BaseModel):
    type: typing.Literal['disk_status_result']
    free_bytes: int
    path: str
    total_bytes: int
    used_bytes: int


class Devices(BaseModel):
    type: typing.Literal['devices']
    devices: list[dict[str, object]]


class KeyLabelSet(BaseModel):
    type: typing.Literal['key_label_set']
    key: str
    label: str


class Marked(BaseModel):
    type: typing.Literal['marked']
    label: str


class MutableAttributesResult(BaseModel):
    type: typing.Literal['mutable_attributes_result']
    mutable_attributes: list[str]


class NoiseFloorSet(BaseModel):
    type: typing.Literal['noise_floor_set']
    channel: int
    noise_floor: float | None
    source: str


class ProfilesReloaded(BaseModel):
    type: typing.Literal['profiles_reloaded']
    profiles_path: str


class RecordingState(BaseModel):
    type: typing.Literal['recording_state']
    paused: bool
    stopped: bool


class StatusSnapshot(BaseModel):
    type: typing.Literal['status_snapshot_result']
    devices: list[dict[str, object]]
    disk: dict[str, object]
    errors: list[str]
    recording: dict[str, bool]
    rows: list[dict[str, object]]


class TrackNames(BaseModel):
    type: typing.Literal['track_names']
    track_names: DeviceTrackNames


class Shutdown(ipc.Shutdown):
    type: typing.Literal['shutdown']


class Error(ipc.Error):
    type: typing.Literal['error']
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
    | Error
)

Message = Hello | RowsMessage | KeyPressed | KeyReleased | Request | Response | Shutdown

MESSAGE = TypeAdapter(Message)


def parse_message(line: str) -> Message:
    return MESSAGE.validate_json(line)
