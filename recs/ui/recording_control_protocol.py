from collections.abc import Callable
from typing import Protocol

from pydantic import ValidationError

from recs.base.errors import ErrorRecord, RecsError
from recs.cfg.cfg import Cfg
from recs.daemon import external_ipc, gui_ipc, gui_protocol

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
    'status_snapshot',
]


class ControlDisplay(Protocol):
    def take_control_requests(self) -> list[gui_ipc.ControlRequest]:
        ...


class RecordingControlTarget(Protocol):
    cfg: Cfg
    shutdown_started: bool
    track_names: dict[str, dict[str, int]]

    def calibrate(self, request: gui_protocol.Calibrate) -> gui_protocol.Calibrated:
        ...

    def device_status(self) -> list[dict[str, object]]:
        ...

    def disk_status(self) -> gui_protocol.DiskStatus:
        ...

    def get_cfg(self, request: gui_protocol.GetCfg) -> gui_protocol.CfgValue:
        ...

    def mark(self, request: gui_protocol.Mark) -> gui_protocol.Marked:
        ...

    def pause_recording(self, reason: str) -> gui_protocol.RecordingState:
        ...

    def reload_profiles(self) -> gui_protocol.ProfilesReloaded:
        ...

    def resume_recording(self, reason: str) -> gui_protocol.RecordingState:
        ...

    def set_cfg(self, request: gui_protocol.SetCfg) -> gui_protocol.CfgSet:
        ...

    def set_key_label(
        self, request: gui_protocol.SetKeyLabel
    ) -> gui_protocol.KeyLabelSet:
        ...

    def set_noise_floor(
        self, request: gui_protocol.SetNoiseFloor
    ) -> gui_protocol.NoiseFloorSet:
        ...

    def set_track_names(
        self, request: gui_protocol.SetTrackNames
    ) -> gui_protocol.TrackNames:
        ...

    def set_tracks(self, request: gui_protocol.SetTracks) -> gui_protocol.TracksSet:
        ...

    def status_snapshot(self) -> gui_protocol.StatusSnapshot:
        ...


class RecordingControlProtocol:
    def __init__(self, control: RecordingControlTarget) -> None:
        self.control = control

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
                    if not self.control.shutdown_started:
                        self.control.shutdown_started = True
                        shutdown()
                    response = gui_protocol.RecordingState(
                        type='recording_state', paused=False
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
            return self.control.calibrate(request)
        if isinstance(request, gui_protocol.Capabilities):
            return gui_protocol.CapabilitiesResult(
                type='capabilities_result',
                commands=API_COMMANDS,
                version=gui_protocol.VERSION,
            )
        if isinstance(request, gui_protocol.DiskStatusRequest):
            return self.control.disk_status()
        if isinstance(request, gui_protocol.GetCfg):
            return self.control.get_cfg(request)
        if isinstance(request, gui_protocol.GetTrackNames):
            return gui_protocol.TrackNames(
                type='track_names', track_names=self.control.track_names
            )
        if isinstance(request, gui_protocol.ListDevices):
            return gui_protocol.Devices(
                type='devices', devices=self.control.device_status()
            )
        if isinstance(request, gui_protocol.MutableAttributes):
            return gui_protocol.MutableAttributesResult(
                type='mutable_attributes_result',
                mutable_attributes=sorted(self.control.cfg.mutable_attributes),
            )
        if isinstance(request, gui_protocol.Mark):
            return self.control.mark(request)
        if isinstance(request, gui_protocol.PauseRecording):
            return self.control.pause_recording('pause_recording')
        if isinstance(request, gui_protocol.ReloadProfiles):
            return self.control.reload_profiles()
        if isinstance(request, gui_protocol.ResumeRecording):
            return self.control.resume_recording('resume_recording')
        if isinstance(request, gui_protocol.SetCfg):
            return self.control.set_cfg(request)
        if isinstance(request, gui_protocol.SetKeyLabel):
            return self.control.set_key_label(request)
        if isinstance(request, gui_protocol.SetNoiseFloor):
            return self.control.set_noise_floor(request)
        if isinstance(request, gui_protocol.SetTrackNames):
            return self.control.set_track_names(request)
        if isinstance(request, gui_protocol.SetTracks):
            return self.control.set_tracks(request)
        if isinstance(request, gui_protocol.StatusSnapshotRequest):
            return self.control.status_snapshot()
        raise RecsError(f'Unsupported request: {request.type}')
