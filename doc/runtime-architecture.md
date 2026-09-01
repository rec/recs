# Runtime Architecture

## Overview

`recs` starts in the CLI, builds a `Cfg`, constructs a `Recorder`, and then lets
the recorder coordinate a set of smaller runtime collaborators. The recorder is
still the top-level owner of the run, but most mutable domains now live outside
`recs/ui/recorder.py`.

Important collaborators:

- `DeviceLifecycle`: source discovery, source child processes, source updates,
  device presence, frame clocks, failures, and buffer status.
- `RecordingSession`: active record, files written, file lifecycle entries,
  session id, and disk-switch continuity.
- `RecordingControl`: GUI and external control requests, recording state,
  mutable configuration, track layout changes, status snapshots, and settings
  persistence.
- `DiskMonitor`: disk-space policy, alert state, emergency thresholds, write
  rate, and removable-disk candidates.
- `DiskControl`: applies disk decisions by stopping sources, draining pending
  updates, closing and opening records, changing output directories, and
  resuming recording when possible.
- `Calibration`: selects tracks for calibration, waits for source results, and
  applies measured noise floors.
- `OscRecorder`: optional per-session UDP OSC recording. It loads the TOML
  passed with `--osc-nodes`, records each node under `osc/`, and polls
  configured requests and feedback subscriptions without affecting audio.

## OSC recording

OSC nodes are configured in TOML because OSC itself does not define device
discovery, ports, queries, or feedback. A node may have startup commands,
periodic polls, periodic subscriptions, or no outbound messages for continuous
telemetry. `resubscribe_period = 10` renews an X18 `/xremote` feedback lease.

```toml
[[nodes]]
name = "x18"
host = "10.43.0.18"
port = 10024

[[nodes.subscriptions]]
path = "/xremote"
resubscribe_period = 10
```

JSONL compression is enabled by default per node. It omits fields unchanged
from the preceding record with the same `kind`; set `jsonl_compression = false`
for a node that needs complete records on every line.

Successful subscriptions are not written to JSONL by default. This avoids
filling an X18 log with keepalive traffic; failed sends and all received packets
remain recorded. OSCQuery is intentionally not implemented.

## Main loop order

The recorder loop keeps this order explicit:

1. Stop if the display has closed.
2. Monitor disk space.
3. Receive key events.
4. Receive GUI and external control requests.
5. Poll devices.
6. Reap exited source children.
7. Stop stalled source children.
8. Update online source state.
9. Wait for source child updates.
10. Receive source updates.

This order gives disk safety and control traffic a chance to run before waiting
for more audio updates.

## Emergency-first draining

Several paths intentionally drain queues or pipes until they are empty:

- GUI and external control requests in `RecordingControl.receive()`;
- source pipes in `DeviceLifecycle._drain()`;
- source-control messages in `SourceRecorder._receive_control_messages()`;
- pending source updates during source shutdown and disk switching.

This is deliberate. When disk space is nearly exhausted, the useful behavior is
to process as much pending state as possible while the user may be inserting a
replacement disk or issuing a final control command. A fairness limit could make
the recorder stop processing emergency state earlier even though it still has a
chance to save the session.

Future latency work should preserve this priority. If any drain loop becomes
bounded, the replacement needs an explicit emergency mode or test coverage that
proves disk switch and source shutdown still drain final source state.

## Parent and child source protocol

The parent owns a `SourceProcess` for each source. A source child runs
`SourceRecorder`, opens the input stream, buffers callback updates, writes files
through `ChannelWriter` instances, and publishes `SourceUpdate` or
`SourceFailure` messages back to the parent.

The parent can send `SourceControl` messages to update child configuration,
track names, calibration requests, or track layouts. Those control messages are
asynchronous. An event entry can show that the parent accepted a change
before every child has applied it.

## Disk switch lifecycle

Disk switching is a high-risk lifecycle operation:

1. Choose an output directory on the target disk.
2. Record `disk_switch_started` in the current record.
3. Stop and join live hardware source processes.
4. Drain pending source updates.
5. Record continuity information in the old record.
6. Finish the old record.
7. Reset session state for the new output directory.
8. Update source configuration.
9. Start the new record.
10. Record completion in the new record.

The stop, drain, and record steps must stay in a strict order so final file
entries are not lost when the current disk is close to full.

## GUI and external IPC flow

The daemon GUI socket is a private GUI transport. External clients should use
the public Recs RPC endpoints documented in `doc/recs_protocol.md`.

Recs is intended to have at most one active control client. A future change
should reject additional clients instead of adding multiclient coordination.

Control request handlers should not mutate recorder state directly from IPC
threads. They queue requests for the recorder loop and wait for the recorder loop
to produce responses.

## Record ownership

`RecordingSession` owns the active record writer and session file bookkeeping.
Other collaborators report events through recorder callbacks, but they should not
write session record files directly.

The record is the recovery and audit source for:

- source lifecycle;
- track activity;
- file start and finish entries;
- warnings and errors;
- disk alerts and disk switches;
- markers;
- runtime control changes;
- calibration results;
- session continuity.

## Current limits

The architecture still has known rough edges:

- `Recorder` exposes some collaborator state for tests and remaining
  orchestration.
- `RecordingControl` still owns several control subdomains.
- `SourceRecorder` combines realtime input buffering, writing, calibration, and
  source-control handling.
- Single-client enforcement is intended but not yet implemented.
- Raspberry Pi CPU and memory limits still need hardware measurement.
