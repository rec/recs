from pathlib import Path

from recs.cfg.cfg import Cfg

from . import disk_space, recording_paths


class DiskMonitor:
    def __init__(self, cfg: Cfg) -> None:
        self.cfg = cfg
        self.alerts_reported: set[tuple[Path, str]] = set()
        self.emergencies_reported: set[Path] = set()
        self.first_alert = False
        self.alert_threshold: str | None = None
        self.last_poll = 0.0
        self.rate = disk_space.WriteRate()
        self.paused = False

    def ready(self, timestamp: float) -> bool:
        if timestamp - self.last_poll < self.cfg.recording.disk_poll_seconds:
            return False
        self.last_poll = timestamp
        return True

    def emergency_threshold(self, disk: disk_space.Disk) -> int:
        values = (
            self.cfg.recording.disk_removable_emergency
            if disk.removable
            else self.cfg.recording.disk_system_emergency
        )
        return max(
            self.cfg.recording.minimum_free_space,
            disk_space.threshold_bytes(values, self.rate.bytes_per_second),
        )

    def pause_threshold(self, disk: disk_space.Disk) -> int:
        values = (
            self.cfg.recording.disk_removable_pause
            if disk.removable
            else self.cfg.recording.disk_system_pause
        )
        return max(
            self.cfg.recording.minimum_free_space,
            disk_space.threshold_bytes(values, self.rate.bytes_per_second),
        )

    def removable_disks(self) -> list[disk_space.Disk]:
        disks = [
            disk_space.disk(path, True)
            for path in recording_paths.mounted_record_disks()
        ]
        return sorted(
            (disk for disk in disks if disk is not None),
            key=lambda d: d.free_bytes,
            reverse=True,
        )

    def recording_disk(self, path: Path) -> disk_space.Disk | None:
        resolved = path.resolve()
        for candidate in recording_paths.mounted_record_disks():
            if resolved.is_relative_to(candidate.resolve()):
                return disk_space.disk(candidate, True)
        return disk_space.disk(path, False)

    def add_sample(self, timestamp: float, disk: disk_space.Disk) -> None:
        self.rate.add(timestamp, disk.total_bytes - disk.free_bytes)

    def new_alerts(self, disk: disk_space.Disk) -> list[str]:
        alerts: list[str] = []
        for threshold in self.cfg.recording.disk_alert_thresholds:
            if disk.free_bytes >= disk_space.threshold_bytes(
                [threshold], self.rate.bytes_per_second
            ):
                continue
            key = (disk.path, threshold)
            if key in self.alerts_reported:
                continue
            self.alerts_reported.add(key)
            self.first_alert = True
            self.alert_threshold = threshold
            alerts.append(threshold)
        return alerts

    def new_emergency(self, disk: disk_space.Disk) -> bool:
        if disk.free_bytes >= self.emergency_threshold(disk):
            return False
        if disk.path in self.emergencies_reported:
            return False
        self.emergencies_reported.add(disk.path)
        return True
