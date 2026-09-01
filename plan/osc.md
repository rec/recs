# OSC Recording

## Scope

Record OSC UDP traffic alongside audio and MIDI for the lifetime of a Recs
recording session. Each configured node writes timestamped JSONL records into
the session's `osc/` directory. The recorder preserves both the received
datagram and the outbound messages that caused or maintained it.

OSC defines message encoding, not device discovery, addresses, ports, queries,
or state feedback. Configuration must therefore describe each node's endpoint
and its device-specific traffic.

## Goals

- Record inbound OSC datagrams as newline-delimited JSON records.
- Record outbound OSC commands in the same stream to retain context.
- Support command-only devices, direct polling, subscription/feedback, and
  continuous telemetry with one configuration model.
- Keep device-specific messages, paths, ports, and timing in configuration.
- Expose node health and recent errors in the existing Recs status surfaces.
- Keep OSC failures independent from audio recording.

## Non-Goals

- Do not implement OSCQuery, mDNS, or automatic device discovery.
- Do not infer a device's OSC address space from packets.
- Do not add device profiles, a generic OSC control UI, playback, or routing.
- Do not decode vendor-specific payload semantics beyond ordinary OSC message
  and bundle decoding.
- Do not use OSC recording as proof that a device is healthy. A received packet
  proves only that a packet arrived.

## Configuration

Add an optional `osc_nodes` TOML file to `Cfg`, with an empty path disabling OSC
recording. The file contains one `[[nodes]]` entry per remote endpoint. `host`
and `port` are the destination for outbound OSC; `bind_port` is the local UDP
port used to receive replies and defaults to `0`, allowing the operating system
to choose it.

```toml
[[nodes]]
name = "x18"
host = "10.43.0.18"
port = 10024

[[nodes.subscriptions]]
path = "/xremote"
resubscribe_period = 10

[[nodes]]
name = "cue-server"
host = "10.43.0.31"
port = 53000

[[nodes.commands]]
path = "/cue/go"
args = [12]
on_start = true

[[nodes]]
name = "processor"
host = "10.43.0.42"
port = 9000

[[nodes.polls]]
path = "/meter/main"
period = 1.0

[[nodes]]
name = "tracking"
bind_port = 7000
```

`args` is a TOML list of OSC scalar values: strings, integers, floats, and
booleans. An omitted `args` sends an empty argument list.

The node forms deliberately cover the four useful device behaviours:

- **Command only:** `commands` sends configured messages. The outbound record
  is still useful even if the device never replies.
- **Direct polling:** each `polls` entry sends its message every `period`
  seconds; returned packets are captured as ordinary inbound records.
- **Subscription/feedback:** each `subscriptions` entry sends its message at
  startup and again every `resubscribe_period` seconds. This supports the X18
  `/xremote` lease without treating it as a universal OSC convention.
- **Continuous telemetry:** a node with no commands, polls, or subscriptions
  simply binds its UDP socket and records the packets it receives.

Allow `commands` to have `on_start = true` only. There is no general recurring
command setting because `polls` and `subscriptions` express the two distinct
recurring behaviours and preserve their intent in configuration.

## Output Format

Create one JSONL file per node under the session directory:

```text
<session>/osc/x18.jsonl
<session>/osc/processor.jsonl
```

Each line has a wall-clock `time`, monotonic receipt or send timestamp,
`direction` (`"in"` or `"out"`), `kind` (`"osc"` or `"error"`), raw
`data_b64`, decoded OSC messages when decoding succeeds, and `source` or
`target` UDP address. Outbound records also identify their reason:
`"command"`, `"poll"`, or `"subscription"`.

Malformed datagrams remain recorded with `data_b64` and a decode error. This is
an evidence file, so a decoder failure must not discard the wire data.

Rotate each node file at the existing session-file size limit, using a numbered
suffix. Retain all parts of the current recording session. Recs' normal session
retention policy, rather than OSC-specific deletion, decides when old sessions
are removed.

## Runtime Architecture

Add `recs/osc/` as a sibling pipeline to `recs/audio/` and `recs/midi/`:

```text
Recorder
  DeviceLifecycle       audio sources
  MidiRecorder          MIDI sources
  OscRecorder           configured OSC nodes
    OscNodeRecorder     one UDP socket and JSONL writer per node
```

`OscRecorder` owns configuration validation, node lifecycle, status aggregation,
and shutdown. `OscNodeRecorder` owns its UDP socket, due commands, non-blocking
receive loop, decoder, and JSONL writer. Use the recorder's main loop to poll
each socket and run due work. Do not add background threads unless a concrete
blocking limitation requires one.

At session start, create the `osc/` directory and output file for every enabled
node before opening sockets. Start-up failures are then visible even for a node
that never receives a packet.

## Record And Status

Extend the record with OSC-specific records rather than overloading audio
file fields:

- `osc_node_started`: name, endpoint, bound address, and output path.
- `osc_node_failed`: name, operation, and error.
- `osc_file_finished`: path, node name, byte count, inbound count, outbound
  count, and decode-error count.

Add per-node status to `status_snapshot`: configured name, endpoint, bound
address, output path, byte count, packet counts by direction, last packet time,
last error, and whether any poll or subscription is overdue. Surface failures
in `recs explain` separately from audio-device failures.

## Error Handling

- A bad node configuration rejects that node before a recording starts and
  reports its exact field error.
- Socket creation, sends, receives, decoding, and file writes record a node
  error and continue other OSC nodes and audio recording.
- A failed periodic send remains due for its next configured interval; do not
  add retries or change the configured cadence.
- A node whose output file cannot be opened is disabled for that session with a
  record error. It must not silently discard packets.

## Tests

Use local UDP sockets and a deterministic monotonic clock:

1. Validate TOML parsing and reject invalid ports, empty names, non-positive
   periods, duplicate names, and unsupported argument values.
2. Verify a command-only node writes its startup outbound record without an
   inbound reply.
3. Verify polling sends at its configured cadence and records a returned OSC
   datagram.
4. Verify a subscription sends at startup and again after
   `resubscribe_period=10`, including the X18 `/xremote` configuration.
5. Verify a telemetry-only node records unsolicited packets.
6. Verify raw malformed data is retained with a decode error.
7. Verify node failures populate status and record entries while audio
   recording continues.
8. Verify output files, rotation, record summaries, and `recs explain`.

## Implementation Order

1. Add the TOML configuration models and validation tests.
2. Add JSONL record and writer tests, including decoded and malformed packets.
3. Add `OscNodeRecorder` with fake sockets and deterministic scheduling tests.
4. Add `OscRecorder` lifecycle, status, and record integration.
5. Integrate it into `Recorder` start, loop, disk-switch, and shutdown paths.
6. Update session inspection and explanation commands for OSC files and errors.
7. Run a bounded manual X18 test that confirms `/xremote` is sent every ten
   seconds and incoming mixer changes grow the X18 JSONL file.

## Additional Work Beyond The Prompt

None.
