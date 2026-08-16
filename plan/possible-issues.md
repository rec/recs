# Possible Code Issues

## Scope

This document lists likely issues in the current `recs` codebase after the
recorder split refactor. It focuses on runtime correctness, CPU and memory use,
race conditions, readability, maintainability, naming, documentation drift, and
features that may conflict with each other.

This is an analysis document. It does not claim every item is a confirmed bug in
normal use. Items that depend on hardware, daemon mode, removable disks, or long
recordings need runtime verification.

## Highest-risk correctness and race issues

### Source shutdown can still lose or reorder final state

`recs/ui/source_process.py` drains child updates only after the child process is
joined or terminated. `recs/ui/source_recorder.py` also batches source updates in
`SourceUpdateTransport` and waits only `UPDATE_DRAIN_TIMEOUT` during finish. This
keeps shutdown fast, but it leaves a narrow window where a final update, file end
frame, calibration result, or buffer warning can be merged, skipped, or arrive
after the parent has already moved on.

The most sensitive callers are disk switch, stop recording, source reap, and
stalled-source handling. Those paths depend on final file records and final
track-stopped events being observed before manifests are closed.

### Disk switching stops all hardware through a synchronous hot path

`recs/ui/disk_control.py` stops and joins each hardware source in
`switch_recording_disk()`, drains pending updates, closes the current manifest,
changes the output directory, and starts a new manifest. That is a lot of
mutable state in one operation. A child process that reaches the two-second join
timeout can be terminated while still trying to flush updates or close files.

The manifest currently records both a pre-close `disk_switch_finished` event and
a post-open `disk_switch_finished` event with different fields. That may be
intentional continuity metadata, but the shared event name makes downstream
consumers more likely to misread the sequence.

### Main-loop draining is unbounded in several places

`RecordingControl.receive()` drains all GUI requests and all external requests in
one call. `DeviceLifecycle._drain()` drains a source pipe until it is empty.
`SourceRecorder._receive_control_messages()` drains all source-control messages
before continuing block processing. In normal traffic this is fine, but a bursty
client or a child emitting many queued updates can monopolize the recorder loop
and delay device polling, disk checks, UI refresh, or audio block processing.

Bounded draining would make latency easier to reason about. If the current
unbounded behavior is required, it should be documented as an intentional
priority decision.

### GUI control requests can block GUI listener threads indefinitely

`recs/daemon/gui_ipc.py` creates a `ControlRequest`, appends it to the daemon
queue, and then the listener thread waits in `wait_for_response()` with no
timeout. If the recorder loop is stopped, hung in shutdown, or busy in a long
disk switch, that listener thread can wait forever. This is probably acceptable
for a local daemon if shutdown tears the process down, but it is a race worth
calling out because it affects control UX and test determinism.

### Live mutable configuration is not snapshot-based

`RecordingControl.set_cfg_value()` mutates the active config, forwards it to
devices, writes a manifest event, optionally saves settings, and updates
recorder callbacks. Source children receive the new config asynchronously through
`SourceControlTransport`. During that interval, different sources can run under
different config snapshots while status and manifest events already report the
new value.

This is especially sensitive for output paths, noise floors, recording timing,
format, and disk thresholds.

## CPU and latency issues

### UI refresh defaults are aggressive for a recorder

`Cfg.console.ui_refresh_rate` defaults to `23.0`. That means row generation,
daemon status publication, GUI broadcasts, and display refresh can happen often
even when recording is the primary job. This is probably fine on a laptop, but it
is worth rechecking on Raspberry Pi targets and during 18-channel recording.

The performance plan already treats local recording as the highest-priority job.
The code should make that priority visible by bounding or measuring UI work.

### Audio block processing repeats per-track reductions

`SourceRecorder._receive_update()` constructs a `Block` for every track, then
each `ChannelWriter` computes maxima, minima, RMS-like volume, noise-floor
checks, and moving averages. For mono or stereo tracks this is simple, but on
many channels the code repeats array slicing and reductions once per track.

This design is readable and keeps `ChannelWriter` independent, but it may cost
more CPU than a source-level reduction that computes per-channel measurements
once and then maps them to tracks.

### File-size bookkeeping may touch the filesystem often

`ChannelWriter._state()` reports `self.files_written.total_size`. If that value
is computed from filesystem stat calls in `recs.misc.file_list`, status updates
can add filesystem overhead proportional to the number of output files. This is
not likely to dominate normal recording, but it can matter in long sessions with
many split files and frequent UI refresh.

### Queue and pipe draining can amplify latency under stress

The child process queues blocks in `InputBuffer`, then sends merged status
through a multiprocessing pipe. The parent may also drain multiple source pipes
and control queues. Under normal load this reduces overhead, but under stress it
can convert a disk stall or slow UI/control client into visible latency spikes.

## Memory and backpressure issues

### InputBuffer is unbounded except for periodic free-memory checks

`InputBuffer` uses an unbounded `Queue`. It drops new blocks only when
`memory.available_bytes()` falls below `memory_reserve_megabytes`, and that check
runs only every `memory_check_period` seconds. This avoids premature drops, but a
fast producer can enqueue many NumPy arrays before the next memory check.

The project has a documented estimate that 18 channels at 48 kHz and 10 seconds
of float32 audio is about 34.6 MB, but Python queue objects, pydantic models, and
per-track blocks add overhead. A bounded queue based on seconds of audio would be
easier to reason about than global free-memory polling alone.

### SourceUpdate merging retains growing lists until transport catches up

`_merge_updates()` preserves file paths, file records, file end frames, warnings,
calibration, and track layout while collapsing many child updates into one
transport message. That is useful for reducing pipe traffic, but when the parent
is busy the pending message can grow with every new file and warning.

This is probably bounded in ordinary recordings because files do not open every
block. It is less obviously bounded during rapid split-file tests or a warning
storm.

### Quiet buffers are stored as Block objects

`ChannelWriter` holds recent quiet audio in `Blocks` for `quiet_before_start` and
`quiet_after_end`. This is necessary for the feature, but the memory cost scales
with channel count, sample width, and configured quiet windows. Large quiet
windows on many tracks can consume more memory than users expect.

### Manifest reading loads the whole file

`recs/ui/session_manifest.py` uses whole-file reads when loading manifest text.
That is simple and fine for ordinary JSONL manifests, but long daemon sessions
or stress tests can create large manifests. Streaming reads would avoid turning
manifest inspection into a memory spike.

## Maintainability and responsibility issues

### Recorder is smaller, but still coordinates too much state

`recs/ui/recorder.py` is still a large orchestration file. It now delegates
device lifecycle, recording control, disk monitoring, disk control, calibration,
and recording sessions, but it still wires many callbacks and retains
compatibility properties exposing collaborator internals.

Those properties make the refactor easier to land, but they also keep old
ownership boundaries alive. Future changes can accidentally bypass the new
collaborators and mutate lifecycle state directly.

### RecordingControl has too many roles

`recs/ui/recording_control.py` handles GUI request intake, external request
intake, request dispatch, configuration mutation, settings persistence,
track-layout validation, noise-floor migration, status snapshots, disk status,
pause/resume/stop, marks, and profile reloads. That is more than "recording
control".

The highest-value split would separate protocol dispatch from recording
operations and from track/config editing. That would also make it easier to test
control behavior without constructing most of the recorder.

### SourceRecorder mixes source IO, buffering, writing, calibration, and control

`recs/ui/source_recorder.py` owns the input stream, callback queue, control pipe,
channel writers, per-track layout changes, calibration measurement, file record
collection, buffer warning generation, and transport merging. This is currently
the hottest path in the program and also one of the hardest files to change
safely.

The immediate risk is not file length alone. It is that realtime audio handling
and control-plane mutation live in the same loop.

### Cfg and CLI duplicate too much structure

`recs/cfg/cfg.py` defines nested configuration models and validators.
`recs/cfg/cli.py` manually mirrors many of those fields into a large Tyro
function. Help text, defaults, mutability, and validation can drift because the
same option exists in several forms.

The comment in `cfg.py` saying "See ./cli.py for full help" confirms the split
is intentional, but it also means documentation for options is not colocated
with the model that validates them.

### Daemon GUI IPC owns both transport and live daemon state

`recs/daemon/gui_ipc.py` accepts clients, tracks client listeners, queues key
events, queues control requests, stores protocol errors, writes daemon status,
broadcasts rows, and forwards rows to external IPC. Locks are present, but the
class still combines transport management with status/state aggregation.

This makes shutdown, testing, and failure handling harder than if listener
management and status publication were separate units.

### Tests are large around old ownership boundaries

`test/ui/test_recorder.py` remains very large. That suggests important behavior
is still mostly tested through `Recorder`, even after several collaborators were
extracted. Large integration-style tests are valuable, but they make narrow
changes expensive and can hide which collaborator owns a behavior.

## Naming and readability issues

### Some state names describe implementation, not domain meaning

Names such as `hardware`, `files`, `sources`, `present`, `failed`, and `frames`
inside `DeviceLifecycle` are concise, but they require local context. For
example, `files` means file sources, not files written, and `hardware` means
input-device source processes, not physical hardware state.

Clearer names would reduce accidental misuse in recorder and control code.

### Recording state flags overlap

`RecordingControl` has `recording_paused`, `recording_stopped`,
`session_stopped`, and `shutdown_started`. Their interactions are subtle:
stopping implies pausing, session stop depends on manifest state, and shutdown
uses a separate once-only guard. This could be a small explicit state machine
instead of independent booleans.

### Disk monitor and disk control names are close

`DiskMonitor` tracks disk policy and thresholds. `DiskControl` applies decisions
and mutates recorder/session/device state. The split is reasonable, but the
names are easy to blur. A reader can miss that `DiskControl` is the side-effect
owner while `DiskMonitor` is mostly policy state.

### Track/channel/source terminology is hard to follow

The code uses source, device, hardware, channel, track, track name, channel
writer, and file source. Each term has a real meaning, but they are used across
config, UI, audio, daemon protocol, and manifests. The meaning is not always
documented at module boundaries, so new code has to infer it from tests.

## Documentation and stale docs

### Handover document is stale

`doc/handover-broken.md` still says the recorder split is incomplete at an
earlier point and lists duplicate methods that have since been removed or moved.
Keeping it as-is risks misleading future agents.

### Split plan now mixes target architecture with completed work

`plan/split-record.md` describes the intended extraction boundaries and end
state. Several phases have already happened, so the document is now useful as
design background but not as an accurate current task list.

### Runtime architecture is not documented in one current place

After the split, there is no short current architecture document that explains
the main loop ordering, parent/child source protocol, disk switch lifecycle,
daemon GUI flow, and manifest ownership. That knowledge is spread across code,
tests, and older plans.

### Operational limits are documented outside code

The Raspberry Pi performance plan includes important CPU, storage, and memory
assumptions. The runtime settings themselves do not make those limits obvious to
users who only see CLI help or daemon status.

## Feature conflicts and low-value complexity

### There are several control surfaces for one recorder

The program supports terminal UI, GUI IPC, external IPC, daemon status files,
key recording, remote display, and direct CLI modes. Each is useful, but together
they create many ways to observe and mutate the same recording state. This
raises the chance of inconsistent snapshots or behavior that is only tested
through one surface.

### Live mutable settings conflict with reproducibility

Runtime mutation of config values is useful for GUI control and calibration, but
it conflicts with the idea that a recording session is reproducible from its
starting CLI/config. Manifest `cfg_set` events help, but source children apply
changes asynchronously and settings persistence can make a one-off experiment
affect later runs.

### Automatic disk switching is powerful but hard to reason about

Automatic disk switching can save a recording, but it changes output paths,
manifest continuity, source process lifecycles, and pause/resume state at the
same time. It also depends on platform-specific removable disk detection.

This feature deserves more isolated runtime tests than simpler configuration
features.

### Key recording has privacy and UX implications

`record_key_all_apps` can record key activity outside the recorder UI. That may
be useful for marking recordings, but it is a surprising capability and may
conflict with user expectations in daemon or shared-machine use.

### Dry-run, calibration, and silence-preview share recording paths

`ChannelWriter` treats dry run, calibration, and silence preview as
`do_not_record`, while source processes and much of the normal recording
lifecycle still run. This reuse is pragmatic, but these modes have different
goals and can obscure which parts of the recording pipeline are active.

## Suggested remediation order

1. Runtime-test disk switching and source shutdown with real child processes,
   including final manifest records and late source updates.
2. Put explicit bounds or time budgets around queue and pipe draining in the main
   loop, or document why unbounded draining is the intended priority.
3. Split `RecordingControl` into protocol dispatch, recording/session commands,
   and track/config editing.
4. Remove or narrow remaining `Recorder` compatibility properties that expose
   collaborator internals.
5. Add a current architecture document and mark old handover material as stale or
   historical.
6. Measure CPU and memory on the Raspberry Pi target with 18-channel input,
   daemon GUI enabled, and disk-switch checks active.

## Additional work beyond the prompt

None.
