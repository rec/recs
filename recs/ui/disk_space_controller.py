import shutil
from collections.abc import Callable
from pathlib import Path

from recs.base import times
from recs.cfg.cfg import Cfg

from . import disk_space, disk_space_policy, recording_paths, recording_session
from .device_lifecycle import DeviceLifecycle
from .recording_control import RecordingControl
from .session_manifest import ManifestEvent, ManifestRecord, timestamp_to_json


class DiskSpaceController:
    def __init__(
        self,
        cfg: Cfg,
        session: recording_session.RecordingSession,
        devices: DeviceLifecycle,
        monitor: disk_space_policy.DiskSpacePolicy,
        recording: RecordingControl,
        write_record: Callable[[ManifestRecord], None],
        warning: Callable[[str], None],
        cfg_changed: Callable[[Cfg], None],
        receive_pending_updates: Callable[[], None],
        start_manifest: Callable[[], None],
        finish_manifest: Callable[[], None],
        manifest_path: Callable[[], Path],
        session_start_time: Callable[[], float],
    ) -> None:
        self.cfg = cfg
        self.session = session
        self.devices = devices
        self.monitor = monitor
        self.recording = recording
        self.write_record = write_record
        self.warning = warning
        self.cfg_changed = cfg_changed
        self.receive_pending_updates = receive_pending_updates
        self.start_manifest = start_manifest
        self.finish_manifest = finish_manifest
        self.manifest_path = manifest_path
        self.session_start_time = session_start_time

    def monitor_disk_space(self) -> None:
        now = times.timestamp()
        if not self.monitor.ready(now):
            return
        if self.monitor.paused:
            for candidate in self.monitor.removable_disks():
                if candidate.free_bytes >= self.monitor.emergency_threshold(candidate):
                    if self.switch_recording_disk(
                        candidate, 'removable_disk_available'
                    ):
                        self.recording.resume_recording(
                            'removable_disk_available', candidate
                        )
                    return
            return
        path = recording_paths.existing_parent(self.manifest_path())
        current = self.monitor.recording_disk(path)
        if current is None:
            self.warning('Cannot read recording disk space')
            return
        self.monitor.add_sample(now, current)
        rate = self.monitor.rate.bytes_per_second
        for threshold in self.monitor.new_alerts(current):
            self.record_disk_event('disk_space_alert', current, threshold, rate)
            self.warning(
                f'Disk space alert on {current.path}: '
                f'{disk_space.free_space(current.free_bytes)} free'
            )

        emergency = self.monitor.emergency_threshold(current)
        if current.free_bytes < emergency:
            if self.monitor.new_emergency(current):
                self.record_disk_event('disk_space_emergency', current, None, rate)
                self.warning(
                    f'Disk space emergency on {current.path}: '
                    f'{disk_space.free_space(current.free_bytes)} free'
                )
            self.handle_disk_emergency(current)
            return
        if self.monitor.first_alert and self.cfg.recording.disk_auto_switch:
            candidates = self.monitor.removable_disks()
            if candidates and candidates[0].free_bytes > current.free_bytes:
                self.switch_recording_disk(
                    candidates[0], 'new_removable_disk_has_more_space'
                )

    def record_disk_event(
        self, event_type: str, disk: disk_space.Disk, threshold: str | None, rate: float
    ) -> None:
        self.write_record(
            ManifestEvent(
                type=event_type,
                timestamp=timestamp_to_json(times.timestamp()),
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

    def handle_disk_emergency(self, current: disk_space.Disk) -> None:
        for candidate in self.monitor.removable_disks():
            if (
                candidate.path != current.path
                and not current.path.is_relative_to(candidate.path)
                and candidate.free_bytes >= self.monitor.emergency_threshold(candidate)
                and self.switch_recording_disk(candidate, 'disk_space_emergency')
            ):
                return
        system = disk_space.disk(Path.home(), False)
        if (
            system is not None
            and system.free_bytes >= self.monitor.emergency_threshold(system)
            and self.switch_recording_disk(system, 'disk_space_emergency')
        ):
            return
        if current.free_bytes >= self.monitor.pause_threshold(current):
            return
        self.recording.pause_recording('disk_space_exhausted', current)
        self.monitor.paused = True

    def switch_recording_disk(self, disk: disk_space.Disk, reason: str) -> bool:
        previous = self.cfg.directory.output_directory
        output = disk.path / self.cfg.general.default_record_directory
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.warning(f'Cannot switch recording disk to {disk.path}: {error}')
            self.write_record(
                ManifestEvent(
                    type='disk_switch_failed',
                    timestamp=timestamp_to_json(times.timestamp()),
                    from_path=previous,
                    to_path=str(output),
                    reason=reason,
                )
            )
            return False
        self.write_record(
            ManifestEvent(
                type='disk_switch_started',
                timestamp=timestamp_to_json(times.timestamp()),
                from_path=previous,
                to_path=str(output),
                from_free_bytes=shutil.disk_usage(
                    recording_paths.existing_parent(self.manifest_path())
                ).free,
                to_free_bytes=disk.free_bytes,
                reason=reason,
            )
        )
        for source in self.devices.hardware.values():
            source.stop()
            source.join()
        self.receive_pending_updates()
        self.finish_manifest()
        self.session.reset(self.session_start_time())
        directory = self.cfg.directory.model_copy(
            update={'output_directory': str(output)}
        )
        cfg = self.cfg.model_copy(update={'directory': directory})
        cfg.__dict__.pop('output_path_pattern', None)
        for source in self.devices.sources.values():
            source.set_cfg(cfg)
        self.cfg_changed(cfg)
        self.start_manifest()
        self.write_record(
            ManifestEvent(
                type='disk_switch_finished',
                timestamp=timestamp_to_json(times.timestamp()),
                from_path=previous,
                to_path=str(output),
                to_free_bytes=disk.free_bytes,
                reason=reason,
            )
        )
        self.warning(f'Switched recording from {previous} to {output}: {reason}')
        self.recording.recording_paused = False
        self.monitor.paused = False
        return True
