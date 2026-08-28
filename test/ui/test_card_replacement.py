from pathlib import Path

import pytest

from recs.cfg.cfg import Cfg
from recs.ui import card_replacement, recording_paths


def test_card_replacement_uses_same_relative_output_path_on_new_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old = tmp_path / 'old-card'
    new = tmp_path / 'new-card'
    output = old / 'recs' / 'audio'
    session = output / '2026-08-28 12-00-00'
    session.mkdir(parents=True)
    new.mkdir()
    replacement = card_replacement.CardReplacement()
    old_disk = recording_paths.MountedDisk(old, 'old-uuid')
    new_disk = recording_paths.MountedDisk(new, 'new-uuid')
    monkeypatch.setattr(recording_paths, 'mounted_disk', lambda path: old_disk)
    mounts = [old_disk]
    monkeypatch.setattr(recording_paths, 'mounted_disks_with_uuid', lambda: mounts)
    cfg = Cfg(
        output_directory=str(output),
        card_replace_poll_seconds=1,
        card_replace_timeout_seconds=300,
    )

    started = replacement.start(cfg, session, 100)
    assert started.old_uuid == 'old-uuid'
    assert replacement.destination(cfg, 100) is None

    mounts[:] = [new_disk]
    destination = replacement.destination(cfg, 101)

    assert destination == card_replacement.CardReplacementDestination(
        new / 'recs' / 'audio', 'replacement_card_available'
    )


def test_card_replacement_falls_back_to_old_card_after_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    old = tmp_path / 'old-card'
    output = old / 'recs'
    session = output / '2026-08-28 12-00-00'
    session.mkdir(parents=True)
    replacement = card_replacement.CardReplacement()
    old_disk = recording_paths.MountedDisk(old, 'old-uuid')
    monkeypatch.setattr(recording_paths, 'mounted_disk', lambda path: old_disk)
    monkeypatch.setattr(recording_paths, 'mounted_disks_with_uuid', lambda: [old_disk])
    cfg = Cfg(output_directory=str(output), card_replace_timeout_seconds=300)

    replacement.start(cfg, session, 100)

    assert replacement.destination(
        cfg, 400
    ) == card_replacement.CardReplacementDestination(output, 'replacement_timeout')
