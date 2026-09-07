# Capture journal format

`session-record.jsonl` is the append-only evidence used to finalize
[`recording.toml`](recording-format.md). Current captures use **version 4**.
Historical version 3 journals are read only by the explicit migration code and
by the browser when a recording references preserved version 3 evidence.

```text
session/
  session-record.jsonl
  recording.toml
  audio/take.wav
  midi/keys-20260907-120000.jsonl
  osc/desk.jsonl
  key/keyboard.jsonl
```

## Encoding and lifecycle

Each nonempty UTF-8 JSONL line is one complete record. Writers flush each line
and periodically fsync. Line order is observation order, not a cross-device
clock mapping. The first line is a header; clean shutdown ends with a footer.

```json
{"type":"header","version":4,"session_id":"take-1","started_at":"2026-09-07T12:00:00.000Z"}
```

Header fields are `type`, `version`, and `started_at`, with optional
`session_id`, `continued_from`, `application`, and `metadata`. A footer has
`type = "footer"`, `ended_at`, and observed `duration_seconds`.

The parser retains valid lines and reports malformed ones. Finalization accepts
one torn JSON line only at the physical end, retaining an explicitly open
recording. Invalid complete records and corrupt interior lines fail. A missing
footer or unfinished file also leaves the recording open. Completed files can
still be verified and exposed; an unfinished file is evidence, not a sealed
asset. No missing samples or packets are synthesized during recovery.

## Typed file records

`AudioFileRecord` and `EventFileRecord` replace the old optional mixture of
audio, MIDI, and OSC metadata. Both carry `type`, `timestamp`, `stream_id`,
`path`, and `format`, with optional human-readable `source`. Paths are relative
to the journal directory and must remain inside it after symlink resolution.

A file has one `file_started` record and one terminal record:

- `file_finished` records actual stored `quantity_count` after the file closes.
- `file_discarded` records an audio file intentionally removed by the minimum
  capture-length policy. It does not claim an asset or an interrupted file.

Audio records use `media_type = "audio"` and require a `clock_id` shared by
tracks from the same device capture. A reconnect starts a distinct clock.
Their other fields are `frame_count`,
`track_name`, ordered `source_channels`, `channels`, `sample_rate`, `bit_depth`,
and finished `audio_spans`. Each span has payload `asset_start`, native `start`,
and stored frame `count`. Payload offsets consecutively cover the file, while
native positions can have gaps. `quantity_count` is the sum of stored frames.
Finalization requires native boundaries and checks them against the payload.

Event records use `media_type = "midi"`, `"osc"`, or `"key"`, and
`format = "recs_events"`. They require a physical `timebase`, `start_tick`,
and `timing_source`; finished records also supply `end_tick` and actual event
`quantity_count`. The half-open extent bounds stored events, not a claim that
nothing happened outside it. Empty fragments may have equal start/end ticks.
Buffered events can predate the new file's opening, so the finished extent
includes their original ticks rather than their later write time.

Unknown media families require a typed schema before journal support is added.
The current parser rejects an arbitrary media string and untyped field bag.

## Native event payloads

Every line is independently readable, with a typed `kind`, integer `tick`, and
unique `ordinal`. Native event clocks have 1,000,000,000 ticks per second.
Ordinals preserve order at equal ticks and continue across rotation and volumes.
The capture clock is not reset when a new output file is opened.

- MIDI stores raw `data` byte integers. The default `system` timing mode stamps
  the host monotonic clock in the input callback, before queueing. The optional
  `mido` mode accumulates supplied source deltas exactly, rounding the absolute
  position once to nanoseconds. It requires a source that supplies meaningful
  deltas; the installed RtMidi-backed Mido callback does not retain them.
- OSC stores raw `data_b64`, `direction`, `endpoint`, observed wall `source_time`,
  decoded messages or decode errors, and optional send `reason`. Receive ticks
  are taken before decoding. Raw bytes remain available when decoding fails.
  Rotation needs no previous-file compression state. Failed sends remain
  diagnostic events rather than successful packet captures.
- Keys store `key` and `press`/`release` action at host observation time. Their
  labelled operational events remain in the journal for diagnostics.

MIDI-file quantization happens only during explicit interchange export:

```sh
recs session export-midi session/recording.toml midi:keys take.mid
```

Export writes a type-0 SMF at 960 ticks per beat and 120 BPM. It rounds absolute
positions before deriving deltas, avoiding accumulated per-message rounding.
It verifies selected payloads and refuses an existing destination.
Real-time MIDI messages, such as MIDI clock, remain in native recordings.
SMF export reports those unsupported messages before creating a destination.

## Audio timelines and clocks

`audio_timeline` records identify a capture stream, `clock_id`, source, track, sample rate,
source channels, native `start`/`end`, and explicit gaps. They are written when
a writer closes or is reconfigured. Known gap reasons distinguish
`silence_suppressed`, `input_overflow` for missing known native ranges, and
`short_capture` for deliberately discarded audio. Unobserved boundaries remain
`unknown`. A PortAudio overflow with no known frame count stays diagnostic;
its duration is not invented.

Each audio source-process instance has its own capture identity and native
sample-frame clock, shared by its tracks. That identity survives output-volume changes. A reconnected
source gets a new identity, because its sample counter restarts. The audio editor
rejects selections spanning independent clocks until alignment is explicit.
File inputs retain their sample-derived timeline without pretending that their
file positions were physical wall-clock observations.

`clock_observation` records contain `timebases` and an `observation` with:

| Field | Meaning |
| --- | --- |
| `source` | Native timebase ID and integer tick |
| `session` | Reference timebase ID and integer tick |
| `timing_source` | How the relationship was observed |
| `uncertainty_ticks` | Optional bound in reference-clock ticks; absent means unknown |
| `segment` | Observation segment, default zero |

`wall` means Unix-epoch nanoseconds. `monotonic` means the host's monotonic
nanosecond counter. Capture brackets host wall-clock readings with monotonic
readings and retains that measurement interval as uncertainty. MIDI observations
relate its native tick to callback receipt. Audio file-boundary observations
retain native frame positions and callback-derived wall time with unknown
uncertainty. These are measured correspondences, not fitted drift curves or a
claim of sample-perfect synchronization between devices.

## Operational records and continuations

`EventRecord` retains typed diagnostic fields for source discovery/failure,
pause/resume, configuration, marks, key transitions, disk events, queue pressure,
and continuation decisions. Unknown event names remain inspectable; unknown
fields are rejected. `WarningRecord` has a message and optional repeat count
and first timestamp. None of these operational summaries replaces payload data.

Volume changes close current files and the current journal. The old journal
names the next one; the new header uses `continued_from`. Ordinary disk
continuations retain the session ID. The explicit `new_session` command creates
a new session ID with the same reciprocal linkage. Finalization translates
journal links to `recording.toml`; portable export rewrites those document links
and keeps original journal bytes unchanged.

## Finalization and checking

Normal recording shutdown and successful edits finalize automatically. For a
stopped, interrupted capture without a document:

```sh
recs session finalize /path/to/session
recs record check /path/to/session/recording.toml
```

Finalization never overwrites an existing document. It hashes finished assets,
checks audio counts/layouts and event extents/order/counts, and retains incomplete
evidence as an open recording. `record check` additionally decodes all audio
and checks all assets and continuation documents. Recovery scans report a missing
or open document even when the journal has a footer. Physical capture, device
latency, and live playout require hardware validation separately.
