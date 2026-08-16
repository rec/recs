import shutil
from typing import TYPE_CHECKING

from recs.base import times
from recs.base.errors import RecsError
from recs.daemon import gui_protocol

from . import disk_space, recording_paths
from .session_manifest import ManifestEvent, timestamp_to_json

if TYPE_CHECKING:
    from .recording_control import RecordingControl


def mark(
    control: 'RecordingControl', request: gui_protocol.Mark
) -> gui_protocol.Marked:
    control.write_record(
        ManifestEvent(
            timestamp=timestamp_to_json(times.timestamp()),
            type='mark',
            label=request.label,
        )
    )
    return gui_protocol.Marked(type='marked', label=request.label)


def pause_recording(
    control: 'RecordingControl',
    reason: str,
    disk: disk_space.Disk | None = None,
) -> gui_protocol.RecordingState:
    control.recording_paused = True
    for source in control.hardware.values():
        if source.running:
            source.stop()
    control.write_record(
        ManifestEvent(
            timestamp=timestamp_to_json(times.timestamp()),
            type='recording_paused',
            label=reason,
            reason=reason,
            current_path=str(control.cfg.directory.output_directory),
            free_bytes=disk.free_bytes if disk else None,
        )
    )
    return recording_state(control)


def resume_recording(
    control: 'RecordingControl',
    reason: str,
    disk: disk_space.Disk | None = None,
) -> gui_protocol.RecordingState:
    if control.session_stopped:
        control.start_recording_session()
    control.recording_paused = False
    control.recording_stopped = False
    control.write_record(
        ManifestEvent(
            timestamp=timestamp_to_json(times.timestamp()),
            type='recording_resumed',
            label=reason,
            reason=reason,
            path=str(control.cfg.directory.output_directory),
            free_bytes=disk.free_bytes if disk else None,
        )
    )
    return recording_state(control)


def stop_recording(control: 'RecordingControl') -> gui_protocol.RecordingState:
    if control.recording_stopped:
        return recording_state(control)
    pause_recording(control, 'stop_recording')
    control.recording_stopped = True
    control.session_stopped = control.session.manifest is not None
    if control.session_stopped:
        for source in control.hardware.values():
            source.join()
        control.receive_pending_updates()
        control.finish_manifest()
    return recording_state(control)


def reload_profiles(control: 'RecordingControl') -> gui_protocol.ProfilesReloaded:
    if not control.cfg.device.profiles.name:
        raise RecsError('Cannot reload profiles without --profiles')
    control.cfg.__dict__.pop('device_profiles', None)
    for source in control.sources.values():
        source.cfg = control.cfg
    return gui_protocol.ProfilesReloaded(
        type='profiles_reloaded', profiles_path=str(control.cfg.device.profiles)
    )


def status_snapshot(control: 'RecordingControl') -> gui_protocol.StatusSnapshot:
    return gui_protocol.StatusSnapshot(
        type='status_snapshot_result',
        disk=disk_status(control).model_dump(exclude={'type'}),
        devices=device_status(control),
        errors=control.error_records(),
        recording=recording_state(control).model_dump(exclude={'type'}),
        rows=control.rows(),
    )


def disk_status(control: 'RecordingControl') -> gui_protocol.DiskStatus:
    path = recording_paths.existing_parent(control.manifest_path()).resolve()
    usage = shutil.disk_usage(path)
    resume_disk = next(
        (
            disk.path
            for disk in control.disk.removable_disks()
            if disk.free_bytes >= control.disk.emergency_threshold(disk)
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
            usage.free / control.disk.rate.bytes_per_second
            if control.disk.rate.bytes_per_second
            else None
        ),
        alert_threshold=control.disk.alert_threshold,
        alert_active=control.disk.first_alert,
        automatic_switch_armed=(
            control.disk.first_alert and control.cfg.recording.disk_auto_switch
        ),
        paused_for_disk_space=control.disk.paused,
        resume_disk=str(resume_disk) if resume_disk else None,
    )


def device_status(control: 'RecordingControl') -> list[dict[str, object]]:
    devices: list[dict[str, object]] = []
    for name, source in sorted(control.sources.items()):
        device = source.source
        devices.append(
            {
                'channels': device.channels,
                'name': name,
                'online': name in control.devices.present,
                'sample_rate': device.samplerate,
            }
        )
    return devices


def recording_state(control: 'RecordingControl') -> gui_protocol.RecordingState:
    return gui_protocol.RecordingState(
        type='recording_state',
        paused=control.recording_paused,
        stopped=control.recording_stopped,
    )
