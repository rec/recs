# Split `recorder.py`

## Goal

Reduce `recs/ui/recorder.py` to the process lifecycle coordinator for a
recording run. Move cohesive state and behavior into small `recs.ui` modules
without changing the CLI, daemon protocol, manifest format, source-recorder
protocol, or recording behavior.

The end state should retain one public entry point:

```python
from recs.ui.recorder import Recorder
```

`Recorder` should own startup, shutdown, the main event loop, and construction
of its collaborators. It should not itself contain device discovery, control
command dispatch, session-manifest bookkeeping, calibration, disk management,
or path-formatting details.

## Constraints

- Do not split `Recorder` into mixin classes. That keeps one large mutable
  object but makes ownership and call order harder to see.
- Give each extracted collaborator one clear owner for its mutable state.
- Keep audio callbacks, block processing, and file writing in their existing
  source-recorder modules.
- Keep `recs.base` independent from `recs.ui`.
- Preserve the current `Recorder` constructor and public methods until callers
  have been deliberately migrated.
- Move tests alongside the behavior they exercise. Do not replace meaningful
  behavioral tests with mocks of new internal methods.

## Proposed module boundaries

### `recs/ui/recording_paths.py`

Move pure path and platform helpers from the bottom of `recorder.py`:

- default output-directory selection
- daemon recording-directory selection
- removable-disk mount discovery
- Windows removable-disk discovery
- timestamped session-directory naming
- manifest-directory formatting
- available-directory selection
- legal output-path formatting
- atomic text writing and folder opening, if their callers are moved with them

This module must not import `Recorder`. It should accept `Cfg`, `Path`, and
timestamps explicitly.

### `recs/ui/recording_session.py`

Extract a `RecordingSession` collaborator that owns:

- `SessionManifestWriter`
- manifest file-start and file-finish bookkeeping
- files written during the current session
- session start time and session id
- output-directory changes for a new recording session or disk switch
- manifest warnings and lifecycle records

It should expose focused operations such as starting/finishing a session,
recording a source update, recording a warning, and returning the current
manifest path. `Recorder` remains responsible for deciding when those actions
occur.

Do not let this class start or stop `SourceProcess` instances. It represents
the output and manifest state only.

### `recs/ui/disk_monitor.py`

Move the disk-space policy currently embedded in `Recorder` into a
`DiskMonitor` collaborator. It should own:

- recent write-rate samples
- alert and emergency de-duplication
- first-alert state and current alert threshold
- disk-paused state
- threshold evaluation and removable-disk selection

It should return decisions rather than mutating recorder state directly:

- no action
- switch to a target disk
- pause recording
- resume on a target disk

`Recorder` applies those decisions by stopping sources, asking
`RecordingSession` to close/open manifests, updating `Cfg.directory`, and
starting sources through the existing device lifecycle. This makes the
disk-space state machine independently testable and avoids a circular import
from the monitor back to `Recorder`.

Move the remaining removable-disk discovery helper into `recording_paths.py`.
Keep generic free-space and threshold conversion in the existing
`disk_space.py`.

### `recs/ui/device_lifecycle.py`

Extract a collaborator responsible for the main-process view of input devices
and source children:

- polling device snapshots
- adding detected sources and restoring tracks
- online/offline and channel-count transitions
- starting, stopping, reaping, and stalled-source detection
- draining source pipes and forwarding source updates/failures
- source frame clocks and active-track transitions

It should expose events or callbacks for warnings, source updates, and track
activity. `Recorder` and `RecordingSession` should remain the sole places that
turn those events into user-visible warnings or manifest records.

The collaborator owns `SourceProcess` instances and device-presence state;
`Recorder` should no longer have direct loops over `self.hardware` except for
top-level shutdown.

### `recs/ui/recording_control.py`

Extract daemon/GUI request handling and mutable recording operations:

- external and GUI connection draining
- request dispatch
- status snapshots
- get/set configuration
- track names, tracks, key labels, and noise-floor changes
- pause, resume, stop, mark, reload-profiles, and shutdown requests
- settings persistence

Use a small explicit interface supplied by `Recorder` and its collaborators,
rather than importing `Recorder` into this module. Keep protocol models in
`recs.daemon.gui_protocol` and do not change message shapes as part of this
refactor.

### `recs/ui/calibration.py`

Extract calibration selection and measurement coordination:

- choosing requested tracks and stereo pairs
- sending calibration commands to source processes
- collecting calibration results and timeout handling
- applying measured per-channel noise floors through the existing mutable-Cfg
  path

It should not own the RPC request format or manifest writing. It returns the
new noise-floor values and calibration outcome to `recording_control.py`.

### `recs/ui/recorder.py`

After extraction, retain only:

- construction and wiring of the collaborators
- `start`, `run`, `_run`, and orderly shutdown
- top-level summary and no-file explanation
- display/key-recorder setup
- main-loop ordering

The loop order must remain explicit: monitor disk state, receive local input
and control traffic, refresh devices, process source updates, and render the
current state.

## Extraction order

1. Add characterization tests for the current main-loop order, device-offline
   transition, disk switch lifecycle, and manifest continuity where coverage is
   not already present.
2. Move pure output-path and removable-mount helpers to `recording_paths.py`.
   Update their direct tests without changing behavior.
3. Extract `RecordingSession` and move manifest/file bookkeeping tests into
   `test/ui/test_recording_session.py`.
4. Extract `DiskMonitor` as a decision-producing state machine. Move
   `test/ui/test_disk_space.py` policy tests there, retaining recorder-level
   tests for applying switch, pause, and resume decisions.
5. Extract `DeviceLifecycle`. Move device polling, source-child, and frame
   clock tests into `test/ui/test_device_lifecycle.py`.
6. Extract calibration coordination, then control request handling. Keep a
   small recorder-level integration suite that sends real protocol messages.
7. Reduce `Recorder` to orchestration and re-check imports to ensure no
   collaborator imports `Recorder`.
8. Run the complete test suite and perform a daemon-mode smoke test with no
   device, a device arriving, a device leaving, and a removable recording disk.

Each phase should be a separate commit. Do not combine extraction with protocol
changes, configuration defaults, disk-policy changes, or audio-processing
changes.

## Acceptance criteria

- `Recorder` is substantially smaller and only coordinates collaborators.
- Each extracted module has direct focused tests.
- No `recs.ui` import cycle exists.
- The public `Recorder` import and CLI runtime flow are unchanged.
- The external daemon/GUI protocol and manifest event schema are unchanged.
- Existing device, calibration, disk-space, persistence, and end-to-end tests
  pass without weakening assertions.
- Daemon operation remains possible with no audio device and continues to
  report device/disc errors through the existing error area.

## Additional work beyond the prompt

None.
