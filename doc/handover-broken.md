# Recorder Refactor Handover

## Historical note

This file is historical. It captures an earlier interrupted refactor state and
must not be treated as the current source of truth. Use
`doc/runtime-architecture.md`, `plan/possible-issues.md`, and the current code
when planning more recorder work.

## Current State

This is an incomplete attempt to implement [the recorder split plan](../plan/split-record.md). Do not treat it as finished.

The working tree was clean when this document was written. `main` was two commits ahead of `origin/main`:

1. `dab5ad5 Extract device lifecycle`
2. `10eca75 Extract recording control`

The full suite passed after each commit: 434 tests, Ruff, formatting, and `ty check recs`.

Earlier committed extractions are present in history:

1. `a80279b Extract recording paths`
2. `4a00a00 Extract recording session`
3. `b61006f Extract disk monitor`
4. `35facd2 Extract calibration`

## Extracted Modules

- `recs/ui/recording_paths.py`: output paths and removable-disk discovery.
- `recs/ui/recording_session.py`: active manifest and session-file bookkeeping.
- `recs/ui/disk_monitor.py`: disk rate and threshold state.
- `recs/ui/calibration.py`: calibration selection and source-response waiting.
- `recs/ui/device_lifecycle.py`: source children, polling, source pipes, frame clocks, presence, and buffer state.
- `recs/ui/recording_control.py`: GUI/external request intake, replies, row publishing, and idempotent external shutdown.

## Device Lifecycle

`Recorder.__init__` constructs `DeviceLifecycle`, passing the existing `SourceProcess` and `DevicePoller` symbols as factories. This preserves tests that monkeypatch symbols in `recs.ui.recorder`.

These active recorder entry points delegate to the lifecycle: `_poll_devices`, `_reap_sources`, `_stop_stalled_sources`, `_receive_pending_updates`, `_receive_connection`, `_receive_source_message`, and `_receive_update`.

`DeviceLifecycle` owns source dictionaries, frame counters, buffer statistics, source clocks, presence state, failure state, and the poller. It calls recorder callbacks only for manifest/session file records, calibration results, warnings, and manifest events.

### Remaining Device Work

`Recorder` still contains obsolete duplicate private methods after `_poll_devices`: `_add_detected_hardware`, `_add_source`, `_record_source_presence`, `_record_buffer_status`, `_source_frame_clock_valid`, `_record_track_activity`, and `_source_time_expired`. They are no longer active and must be removed after checking callers.

The properties near the top of `Recorder` expose lifecycle state for remaining orchestration/control code. Retain only properties needed outside `DeviceLifecycle`. Do not turn them into stored aliases.

Initial source layout restoration still calls `Recorder._restored_tracks` before `DeviceLifecycle` is built. Move it into `DeviceLifecycle` so it owns all source construction.

The buffer-overflow callback retains the established manifest fields. Do not replace those fields with a generic `value` payload.

## Recording Control

`RecordingControl.receive()` owns GUI/external request draining, protocol-error logging, replies, and once-only external shutdown. `RecordingControl.publish()` owns status row publication.

`Recorder._handle_control_request` still dispatches request types. The following operations remain in `Recorder` and must move with their mutable state into `RecordingControl`:

- pause, resume, and stop
- marks
- config get/set and settings persistence
- key labels
- track names and layouts
- noise floors
- profile reload
- status snapshots and device/disk status

Do not implement a dispatcher that simply calls existing recorder methods. Give `RecordingControl` a small explicit interface for configuration changes, `DeviceLifecycle`, `RecordingSession`, manifest warnings/events, status rows, and settings persistence. `Recorder` should then retain only top-level startup, shutdown, display/key setup, and loop ordering.

## Required End State

- No `recs.ui` import cycle.
- External protocol and manifest schema unchanged.
- `Recorder` is orchestration only, without device, disk, calibration, session, or control state.
- Focused tests accompany extracted behavior.
- Full suite passes.

## Verification

Run after every phase:

    uv run pytest
    uv run ruff check --fix --select B,E,F,I recs test*
    uv run ruff format
    uv run ty check recs
    version=$(cat .python-version)
    version=${version//./}
    find test recs -name '*.py' | xargs uv run pyupgrade --py${version}-plus
    git diff --check

The formatter may reorder imports in `test/audio/test_channel_writer.py`. Do not leave that unrelated two-line change dirty. Keep commits separate by phase. Do not push, pull, switch branches, or use a worktree.
