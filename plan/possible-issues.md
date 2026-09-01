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
revision record events, distinct disk-switch continuation events, bounded
audio callback buffering, bounded merged source-update metadata, streaming
record reads, initial source-recorder and GUI-server splits, clearer
`DeviceLifecycle` state names, the explicit recording runtime-state object, the
current glossary, and the current runtime architecture document.

## Operational and feature-boundary risks

### Automatic disk switching still needs hardware fault-injection tests

Automatic disk switching can save a recording, but it changes output paths,
record continuity, source process lifecycles, and pause/resume state at the
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
errors can flood status and records. The system should rate-limit identical
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
   final record entries, and late source updates.
3. Replace per-record-entry `fsync` with bounded batching plus final durable
   flush and visible record-write failures.
4. Add external RPC request deadlines that mirror GUI control timeout behavior.
5. Improve source child failure diagnostics: exception type, exit code, final
   frame count, last callback timestamp, and expected versus forced stop.
6. Add device-query backoff, latest-only queues, and stable device identity.
7. Add startup-failure status records and a preflight command for show setup.
8. Measure CPU and memory on the Raspberry Pi target with 18-channel input,
   daemon GUI enabled, and disk-switch checks active.
## Additional work beyond the prompt

None.
