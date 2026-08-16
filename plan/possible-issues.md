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

## Maintainability and responsibility issues

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
