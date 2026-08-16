# Disk-space handling plan

This plan describes how `recs` should behave as recording storage fills up.
The goal is to preserve recording when possible, make every storage decision
visible to the user, and record the full disk-space lifecycle in the session
manifest.

## Goals

- Warn early enough that a user can insert a new USB disk before recording is at
  risk.
- Automatically move recording to a better removable disk after disk-space
  alerts have started.
- Treat system disks and removable disks differently: removable recording disks
  can safely get much closer to zero free space than the system disk.
- Enter an emergency mode before writes fail.
- Pause recording only after all usable removable disks and the system fallback
  are too full.
- Resume automatically when a new removable disk with enough space appears.
- Make every threshold, warning, switch, emergency, pause, and resume visible in
  the console, GUI/TUI error area, and session manifest.

## Definitions

- Current disk: the filesystem that contains the active output directory for a
  recorder.
- Removable disk: a mounted external/removable candidate found by the platform
  disk scanner.
- System disk: the normal fallback disk, usually `Path.home()` or the configured
  daemon record directory when no removable disk is usable.
- Remaining space: free bytes reported by the filesystem containing an output
  directory.
- Remaining time: estimated recording time left on a disk at the current write
  rate.
- First alert: the earliest configured disk-space threshold that has been
  crossed for the current disk during this recording session.

## Configuration

All thresholds should be configurable. Each threshold should accept either a byte
amount or a time amount.

Examples:

- `50GB`
- `500MB`
- `10m`
- `30s`

Time thresholds are converted to required free space using the recent measured
write rate for the session. The implementation should use a conservative recent
window, not the whole-session average, so sudden format or channel changes are
reflected quickly.

Configuration groups:

- Alert thresholds: ordered from least severe to most severe.
- Emergency thresholds: separate values for removable disks and the system disk.
- Pause threshold: the point at which the current disk is no longer safe to
  write.
- Disk-switch policy: whether automatic switching is enabled after the first
  alert.
- Disk candidates: mount roots and filters used to decide which disks are
  removable recording candidates.
- Polling period: how often free space and removable disks are checked.

Suggested defaults:

- Alerts: `30m`, `10m`, `2m`.
- Removable emergency: `200MB` or `30s`.
- System emergency: `2GB` or `2m`.
- Pause threshold: equal to emergency unless configured separately.
- Automatic switching: enabled after the first alert.

The actual defaults should be chosen after testing on the Raspberry Pi 5 target
with the expected audio format and device count.

## Alert lifecycle

Disk monitoring should run throughout recording.

For each threshold crossed on the current disk:

1. Print a console warning.
2. Show the warning in the GUI/TUI error area.
3. Write a manifest event.
4. Mark the first alert as active if this was the earliest crossed threshold.

Alerts should be level-triggered with de-duplication. A threshold should not
spam every polling interval, but if recording switches to another disk and that
disk later crosses the same threshold, the alert should be recorded for the new
disk.

Manifest event:

```json
{
  "type": "disk_space_alert",
  "timestamp": "...",
  "path": "/media/tom/USB/recs/...",
  "disk": "/media/tom/USB",
  "free_bytes": 123456789,
  "estimated_seconds_remaining": 612.5,
  "threshold": "10m",
  "severity": "warning"
}
```

## Automatic switching after first alert

Before the first alert, `recs` should keep recording to the selected output
directory. This avoids surprising path changes while space is healthy.

After the first alert, any newly inserted removable disk should be considered for
automatic use. If it has more free space than the current disk and is above the
removable emergency threshold, recording should switch to it.

Switch behavior:

1. Finish any active files on the current disk cleanly.
2. Record a manifest event on the current manifest before switching.
3. Start a new output directory on the target disk.
4. Continue recording new files on the target disk.
5. Create or continue a manifest on the target disk.
6. Include enough manifest information to link the session across disks.

Manifest events:

```json
{
  "type": "disk_switch_started",
  "timestamp": "...",
  "from_path": "/media/tom/OLD/recs/...",
  "to_path": "/media/tom/NEW/recs/...",
  "reason": "new_removable_disk_has_more_space",
  "from_free_bytes": 123456789,
  "to_free_bytes": 64000000000
}
```

```json
{
  "type": "disk_switch_finished",
  "timestamp": "...",
  "from_path": "/media/tom/OLD/recs/...",
  "to_path": "/media/tom/NEW/recs/..."
}
```

If switching fails, record `disk_switch_failed`, keep recording on the current
disk if it is still above the pause threshold, and continue monitoring.

## Emergency behavior

Emergency means the current disk is too close to full to trust normal operation.
The emergency threshold is intentionally different for removable and system
disks:

- Removable disks can get closer to zero because filling them should not damage
  the running OS.
- System disks need a larger reserve so the Raspberry Pi and desktop system keep
  functioning.

When the current disk reaches emergency:

1. Print and display an emergency error.
2. Write `disk_space_emergency` to the manifest.
3. Look for any removable disk above the removable emergency threshold.
4. If one exists, switch to the removable disk with the most free space.
5. If no removable disk is usable and the current disk is removable, switch to
   the system disk if it is above the system emergency threshold.
6. If the system disk is the only remaining option and it is above the system
   emergency threshold, switch to it.
7. If no disk is usable, pause recording.

Manifest event:

```json
{
  "type": "disk_space_emergency",
  "timestamp": "...",
  "path": "/media/tom/USB/recs/...",
  "disk": "/media/tom/USB",
  "disk_kind": "removable",
  "free_bytes": 12345678,
  "estimated_seconds_remaining": 18.3,
  "threshold": "30s"
}
```

## Pause and resume

If every removable disk is below its emergency threshold and the system disk is
below its emergency threshold, recording should pause instead of writing until
the filesystem fails.

Pause behavior:

1. Stop active source recorders cleanly.
2. Finish active file and track lifecycle manifest events.
3. Write `recording_paused` with reason `disk_space_exhausted`.
4. Keep the main recorder process alive.
5. Keep polling for removable disks.
6. Keep the GUI/TUI open and show the emergency state.

Resume behavior:

1. When a removable disk appears above the removable emergency threshold, choose
   the removable disk with the most free space.
2. Start a new output directory there.
3. Write `recording_resumed`.
4. Restart source recorders.
5. Continue normal disk monitoring.

The system disk should not automatically resume recording after a full pause.
After pausing because all disks are exhausted, the recorder should wait for a
removable disk so the system disk is protected.

Manifest events:

```json
{
  "type": "recording_paused",
  "timestamp": "...",
  "reason": "disk_space_exhausted",
  "current_path": "/home/tom/recs/...",
  "free_bytes": 98765432
}
```

```json
{
  "type": "recording_resumed",
  "timestamp": "...",
  "reason": "removable_disk_available",
  "path": "/media/tom/USB/recs/...",
  "free_bytes": 64000000000
}
```

## Manifest continuity

Disk switching creates a practical manifest problem: the current manifest may be
on the disk that is about to fill up.

The implementation should keep manifest writes small and synchronous, but it
also needs a cross-disk continuity model:

- Every manifest should include a session id in the header.
- Every disk switch should be recorded in both the old manifest and the new
  manifest when possible.
- The new manifest should include a `continued_from` field pointing to the
  previous manifest path and last known manifest record id.
- The old manifest should include `continued_at` when the switch succeeds.
- If the old disk is too full to write the final switch event, the new manifest
  should still contain enough information to reconstruct the switch.

This allows a session browser or recovery tool to stitch together a single
logical recording session across multiple disks.

## User-visible status

The GUI and TUI should show:

- Current output disk.
- Free bytes.
- Estimated time remaining.
- Current disk-space alert level.
- Whether automatic disk switching is armed.
- Whether recording is paused for disk space.
- The disk that will be used if recording resumes.

Console messages should match the same events written to the manifest.

## Implementation phases

1. Add disk identity and free-space measurement helpers.
2. Add configurable thresholds that accept bytes or time.
3. Add write-rate estimation and remaining-time calculation.
4. Add warning levels and manifest events without switching behavior.
5. Add removable disk discovery refresh while recording.
6. Arm automatic switching after the first alert.
7. Implement clean output-directory switching for new files.
8. Add emergency fallback from removable disks to other removable disks, then to
   the system disk.
9. Add pause and removable-disk resume behavior.
10. Add cross-disk manifest continuity.
11. Add GUI/TUI status fields for disk space and pause state.
12. Add Raspberry Pi field tests with a small removable disk or loopback mount.

## Open questions

- What exact removable-disk detection should be used on Linux: mount roots only,
  `/sys` removable flags, `lsblk`, or a combination?
- Should automatic switching require the new disk to exceed the current disk by
  an absolute margin, not merely one byte?
- Should the first alert arm switching for the rest of the session or only while
  the current disk remains below the alert threshold?
- Should recordings switch immediately at emergency even if an active file is in
  progress, or should the active file finish if the estimated remaining time is
  still above a short grace period?
- How much system-disk reserve is safe on the Raspberry Pi 5 with 2 GB RAM?
