# Possible Code Issues

## Scope

This document lists likely remaining issues in the current `recs` codebase. It
focuses on runtime correctness, CPU and memory use, race conditions,
readability, maintainability, naming, documentation drift, and features that may
conflict with each other.

This is an analysis document. It does not claim every item is a confirmed bug in
normal use. Items that depend on Raspberry Pi hardware, daemon mode, removable
disks, network failure, or long recordings still need runtime verification.

Resolved items from earlier reviews have been removed. That includes the GUI and
external single-client guards, GUI shutdown-response timeout, live config
revision manifest events, distinct disk-switch continuation events, bounded
audio callback buffering, bounded merged source-update metadata, streaming
manifest reads, initial source-recorder and GUI-server splits, clearer
`DeviceLifecycle` state names, the explicit recording runtime-state object, the
current glossary, and the current runtime architecture document.

## Highest-risk correctness and race issues

### External control requests can still wait forever

GUI control requests now have a finite wait policy, and the transports reject
extra simultaneous clients. External RPC control requests still block in
`ExternalServer.rpc_response()` until the recorder loop responds or the external
server stops.

That is no longer a multiclient scaling issue, but it remains a single-client
lifecycle issue if the recorder loop is blocked in storage, shutdown, or a long
disk switch. External RPC should mirror the GUI timeout/error behavior.

### Startup settings failures may restart without useful durable state

Invalid JSON, invalid saved attributes, unreadable settings, missing configured
files, or unwritable settings paths can raise during startup or settings save.
Systemd may restart the daemon, but a separate local status snapshot may not
explain the loop.

Startup failures should write a small durable failed-status record before exit.
Later settings-save failures should keep the in-memory recording configuration,
report the failure, and avoid becoming a silent API failure.

## CPU, latency, and memory issues

### Disk-stall observability is missing

The recorder does not currently expose write latency, callback queue high-water
marks over time, or per-source dropped-frame trends as first-class emergency
signals. A sustained queue increase should become visible before actual drops.

This overlaps with disk failover: the system needs evidence that a disk is slow
or failing, not just low on free space.

### UI refresh defaults need target measurement

`Cfg.console.ui_refresh_rate` defaults to `23.0`. Row generation, daemon status
publication, GUI broadcasts, and display refresh can happen frequently even
when recording is the primary job. This is probably fine on a laptop, but it
needs measurement on Raspberry Pi targets during 18-channel recording.

### Audio block processing repeats per-track reductions

`SourceRecorder._receive_update()` constructs a `Block` for every track, then
each `ChannelWriter` computes maxima, minima, RMS-like volume, noise-floor
checks, and moving averages. For mono or stereo tracks this is simple, but on
many channels the code repeats array slicing and reductions once per track.

This design is readable and keeps `ChannelWriter` independent, but the cost
should be measured before changing the hot path.

### File-size bookkeeping still stats the active file

`FileList.total_size` already caches completed files, so the old concern about
restatting every file is resolved. It still stats the active last file during
status generation. That is probably fine, but it should stay on the measurement
list if long sessions show status refresh overhead.

### Quiet buffers are stored as Block objects

`ChannelWriter` holds recent quiet audio in `Blocks` for `quiet_before_start`
and `quiet_after_end`. This is necessary for the feature, but the memory cost
scales with channel count, sample width, and configured quiet windows. Large
quiet windows on many tracks can consume more memory than users expect.

### Source and event transport backpressure is hard to see

Source updates coalesce, which protects capture liveness, but it hides how long
the parent has been unable to consume source state. Event-subscriber writes can
also become part of the recorder publication path. A stalled local client should
not delay recording or status publication.

The code needs explicit queue/pipe age and blocked-write metrics, bounded or
disconnectable event delivery, and tests for stopped parent, stopped child, and
non-reading event clients.

### Device query process has no backoff or bounded result queue

`DeviceQueryStream` restarts after missing updates, but repeated PortAudio
failure can still create restart churn. Its internal queue is unbounded if the
polling loop stops consuming snapshots.

It should keep only the newest device snapshot, report child exit detail, and
use restart backoff. Device querying should also be verified not to open a
capture stream or materially compete with the X18 source process.

## Maintainability and responsibility issues

### Recorder still exposes collaborator internals

`recs/ui/recorder.py` delegates device lifecycle, recording control, disk
monitoring, disk control, calibration, and recording sessions, but it still has
compatibility properties exposing collaborator internals.

Those properties make refactoring easier, but they keep old ownership
boundaries alive. Future changes can accidentally bypass the intended
collaborators and mutate lifecycle state directly.

### RecordingControl still has several roles

`recs/ui/recording_control.py` now has clearer runtime state and delegates many
operations, but it still acts as the central control target for GUI requests,
external requests, request dispatch, configuration mutation, settings
persistence, track layout edits, status snapshots, disk status, pause/resume,
marks, and profile reloads.

The next split should separate protocol dispatch, recording/session commands,
and track/config editing more strongly.

### SourceRecorder still mixes realtime and control-plane work

`recs/ui/source_recorder.py` now has smaller helpers for input buffering,
calibration, file-event collection, and update transport. It still owns the
input stream, control pipe, channel writers, per-track layout changes, buffer
warning generation, and transport publishing in one realtime loop.

The remaining risk is that realtime audio handling and control-plane mutation
still share one source-child loop.

### Cfg and CLI duplicate too much structure

`recs/cfg/cfg.py` defines nested configuration models and validators.
`recs/cfg/cli.py` manually mirrors many of those fields into a large Tyro
function. Existing tests catch field drift, but help text, defaults, mutability,
and validation still live in multiple places.

### Daemon GUI IPC still combines status publication and transport

`recs/daemon/gui_ipc.py` now has a smaller connection-state helper and rejects
extra GUI clients. The server still accepts clients, writes daemon status,
broadcasts rows, queues control requests, records protocol errors, and forwards
rows to external IPC.

Status publication and recorder-control queueing are still close enough that
shutdown and failure handling require careful tests.

### Tests are still large around old ownership boundaries

`test/ui/test_recorder.py` remains very large. Large integration-style tests are
valuable, but they make narrow changes expensive and can hide which collaborator
owns a behavior. More cases should move to focused collaborator tests while
leaving a smaller recorder-level integration suite.

## Naming, identity, and readability issues

### Device identity is based on mutable display names

Sources are keyed by device name. Replugging, ALSA renumbering, duplicate USB
names, or an edited alias can cause a device to be treated as a different
source, losing track layout/calibration association or attaching to the wrong
device.

The code needs a stable device identity when the host API supplies one. Display
names should remain user-facing labels.

### Disk monitor and disk control names are close

`DiskMonitor` tracks disk policy and thresholds. `DiskControl` applies decisions
and mutates recorder/session/device state. The split is reasonable, but the
names are easy to blur. A reader can miss that `DiskControl` is the side-effect
owner while `DiskMonitor` is mostly policy state.

### Track/channel/source terminology still needs local discipline

`doc/glossary.md` now defines the main terms, but the code still uses them
across config, UI, audio, daemon protocol, and manifests. New code should keep
module boundaries aligned with that glossary instead of reusing terms loosely.

## Operational and feature-boundary risks

### Automatic disk switching still needs hardware fault-injection tests

Automatic disk switching can save a recording, but it changes output paths,
manifest continuity, source process lifecycles, and pause/resume state at the
same time. It also depends on platform-specific removable disk detection.

The code has isolated unit tests, but it still needs Pi/X18/USB-media tests for
full, unplugged, read-only, slow, and remounted disks while recording.

### Singleton ownership is not yet an operator-facing preflight

The control transports reject extra clients, but two daemon starts or stale
service state can still confuse an operator if ownership is not visible in the
status path and service response.

A preflight command should check service state, writable output disk, configured
devices, settings validity, and expected singleton ownership before a show.

### Error floods can hide first cause

Malformed control commands, repeated device failures, disk warnings, or protocol
errors can flood status and manifests. The system should rate-limit identical
errors while preserving first timestamp, most recent timestamp, and count.

### Recs must stay local when networks fail

Recs itself uses local sockets, but Showco and other suite programs may wait on
network actions or status checks. Recording must continue when Wi-Fi, Ethernet,
DNS, remote update, or streaming fails. Local status freshness should be
reported separately from failed network operations.

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

1. Add disk-stall observability: write latency, callback queue high-water marks,
   dropped-frame trends, and emergency reporting before overflow.
2. Runtime-test disk switching and source shutdown with real child processes,
   final manifest records, and late source updates.
3. Replace per-record manifest `fsync` with bounded batching plus final durable
   flush and visible manifest-write failures.
4. Add external RPC request deadlines that mirror GUI control timeout behavior.
5. Improve source child failure diagnostics: exception type, exit code, final
   frame count, last callback timestamp, and expected versus forced stop.
6. Add device-query backoff, latest-only queues, and stable device identity.
7. Add startup-failure status records and a preflight command for show setup.
8. Measure CPU and memory on the Raspberry Pi target with 18-channel input,
   daemon GUI enabled, and disk-switch checks active.
9. Continue ownership cleanup: narrow `Recorder` compatibility properties,
   split `RecordingControl`, and move more recorder tests to collaborator tests.

## Additional work beyond the prompt

None.
