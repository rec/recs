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

### Recs must stay local when networks fail

Recs itself uses local sockets, but Showco and other suite programs may wait on
network actions or status checks. Recording must continue when Wi-Fi, Ethernet,
DNS, remote update, or streaming fails. Local status freshness should be
reported separately from failed network operations.

## Remaining validation

1. Exercise disk switching on the Raspberry Pi with an X18 and real USB media,
   including full, unplugged, read-only, slow, and remounted disks.
2. Measure CPU and memory on the Raspberry Pi target with 18-channel input,
   daemon GUI enabled, and disk-switch checks active.
## Additional work beyond the prompt

None.
