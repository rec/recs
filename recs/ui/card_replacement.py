from dataclasses import dataclass
from pathlib import Path

from recs.base.errors import RecsError
from recs.cfg.cfg import Cfg
from recs.daemon import gui_protocol

from . import recording_paths, session_manifest


@dataclass(frozen=True)
class CardReplacementDestination:
    output_directory: Path
    reason: str


class CardReplacement:
    def __init__(self) -> None:
        self.active = False
        self.deadline = 0.0
        self.next_poll = 0.0
        self.old_mount: recording_paths.MountedDisk | None = None
        self.output_relative = Path()
        self.use_old_mount_immediately = False

    def start(
        self, cfg: Cfg, session_directory: Path, timestamp: float
    ) -> gui_protocol.CardReplaceStarted:
        if self.active:
            raise RecsError('A card replacement is already in progress')
        if (disk := recording_paths.mounted_disk(session_directory)) is None:
            raise RecsError(
                'Current output directory is not on a mounted recording disk'
            )
        try:
            output = Path(cfg.directory.output_directory).resolve()
            output_relative = output.relative_to(disk.path.resolve())
        except ValueError as error:
            raise RecsError(
                'Current output directory is not on the recording disk'
            ) from error
        self.active = True
        self.deadline = timestamp + cfg.recording.card_replace_timeout_seconds
        self.next_poll = timestamp
        self.old_mount = disk
        self.output_relative = output_relative
        self.use_old_mount_immediately = False
        return gui_protocol.CardReplaceStarted(
            type='card_replace_started',
            deadline=session_manifest.timestamp_to_json(self.deadline),
            old_mount=str(disk.path),
            old_uuid=disk.uuid,
        )

    def start_after_unmount(
        self,
        cfg: Cfg,
        output_directory: Path,
        old_mount: recording_paths.MountedDisk,
        timestamp: float,
    ) -> None:
        if self.active:
            return
        try:
            output_relative = output_directory.resolve().relative_to(
                old_mount.path.resolve()
            )
        except ValueError as error:
            raise RecsError(
                'Current output directory is not on the recording disk'
            ) from error
        self.active = True
        self.deadline = timestamp + cfg.recording.card_replace_timeout_seconds
        self.next_poll = timestamp
        self.old_mount = old_mount
        self.output_relative = output_relative
        self.use_old_mount_immediately = True

    def destination(
        self,
        cfg: Cfg,
        timestamp: float,
        replacement_uuids: set[str] | None = None,
    ) -> CardReplacementDestination | None:
        if not self.active or timestamp < self.next_poll:
            return None
        self.next_poll = timestamp + cfg.recording.card_replace_poll_seconds
        assert self.old_mount is not None
        for disk in recording_paths.mounted_disks_with_uuid():
            if (
                disk.uuid != self.old_mount.uuid
                and (replacement_uuids is None or disk.uuid in replacement_uuids)
            ) or (disk.uuid == self.old_mount.uuid and self.use_old_mount_immediately):
                self.active = False
                return CardReplacementDestination(
                    disk.path / self.output_relative,
                    (
                        'original_card_remounted'
                        if disk.uuid == self.old_mount.uuid
                        else 'replacement_card_available'
                    ),
                )
        if timestamp < self.deadline:
            return None
        for disk in recording_paths.mounted_disks_with_uuid():
            if disk.uuid == self.old_mount.uuid:
                self.active = False
                return CardReplacementDestination(
                    disk.path / self.output_relative, 'replacement_timeout'
                )
        return None
