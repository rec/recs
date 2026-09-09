# Recording and sequence documents

The initial common format supports arrangements, recording descriptions, and
ordered event sequences. TOML is the document syntax; `format = "recs"`,
`version = 2`, `kind`, `id`, and `name` form its common envelope. The model's
`document_schema()` function generates JSON Schema for all three kinds.
The [arrangement format](arrangement-format.md) describes audio editing.

`recording.toml` is the content index used by session browsing, checking,
export, and the editor's session resolver. Recording shutdown and successful
audio edits finalize this document beside their version 4 capture journal.
The journal remains append-only operational evidence for diagnostics and
recovery. Content readers require the common document; they do not fall back
to historical journals. Convert old sessions explicitly before opening them.

Finalization hashes finished assets and checks audio metadata and native spans.
It never overwrites an existing document. A failed finalization leaves the
journal and media available; the recorder reports the error, and the next
recovery scan reports the missing document even if the journal has a footer.
`recs record check` performs the fuller payload verification described below.

## Recording fields

| Field | Meaning |
| --- | --- |
| `assets` | Sealed payloads: local ID, path relative to the document directory, encoding, byte length, SHA-256 |
| `timebases` | Named physical clocks with exact positive rational ticks per second |
| `body.state` | `sealed` requires an end timestamp and no unfinished files; otherwise `open` |
| `body.started_at`, `ended_at` | Observed session wall-clock timestamps; not sample alignment |
| `body.observed_duration_seconds` | Optional operational elapsed time, never an event count |
| `body.journal` | Asset ID of the preserved capture journal |
| `body.streams` | Typed audio or event streams, each with a local ID and original opaque `source_id` |
| `body.clock_observations` | Optional source/session tick observations with uncertainty and timing source; no automatic drift fit |
| `body.unfinished_files` | Original stream ID, original journal path, and observed opening timestamp; these are evidence, not verified asset references |
| `body.continued_from`, `continued_at` | Previous and following `recording.toml` paths, resolved relative to this document; they may cross volume roots |

Audio streams have an `AudioType`, native `end` frame, captured fragments, and
explicit gaps. A fragment references an asset and records `asset_start`, stream
`start`, and `count`. All are nonnegative integer frames; `asset_start` defaults
to zero. Gaps are half-open intervals with a reason: `unknown`,
`silence_suppressed`, `input_overflow`, `short_capture`, or `disconnected`. The fragments and gaps
must cover the declared extent without a gap intersecting captured audio.
Exact alternate encodings may overlap only with the same explicit
`variant_group`; other overlapping captures are invalid.

Optional audio `source_name` and `track_name` retain human-facing selectors.
When absent, selection uses the opaque `source_id` and local stream `id`
respectively; it does not split source IDs on punctuation. New audio capture
records exact spans through silence trimming. Several fragments may reference
different offsets in the same file, so the renderer seeks to `asset_start`
before placing each fragment on the native timeline.

When a historical file's actual frame count differs from its journal span,
`unmapped_fragments` preserves its asset, decoded `count`, original
`journal_range`, and reason `frame_count_mismatch`. That journal range is
evidence of the old observation, not a mapping of individual samples. Such a
recording can contain fully verified files while its timeline is unresolved.
The timeline renderer rejects those streams until placement is explicitly
resolved. It does not stretch the file or guess where gaps belong.

Event streams declare `event_schema` and ordered fragments. Native captures also
set `event_kind` to `midi`, `osc`, `key`, `trigger`, `release`, or
`control_change`. Omit it for a mixed-kind stream. Each fragment has an asset,
`event_count`, and matching `timing`. Native fragments require `start` and `end`
in the stream timebase: a half-open stored-event range, empty only when the
count is zero. Counts never substitute for duration:

| Schema | Timing | Interpretation |
| --- | --- | --- |
| `midi` | `smf` | Existing SMF delta ticks and tempo metadata remain in the original file |
| `osc` | `osc_jsonl` | Existing packet timestamps and raw bytes remain in JSONL, including compression state across fragments |
| `recs_events` | `recs_events` | JSONL of the common event envelopes, with a required stream `timebase` |

External MIDI and OSC streams do not claim a document timebase. Their observed
opening timestamp and timing-source label can be retained separately. Native
event JSONL uses the same event records as sequences below, one complete record
per line. Verification checks ordering and unique ordinals across fragments.
Production MIDI, OSC, and key capture now write this common event representation.
MIDI defaults to host monotonic callback timestamps; the optional Mido-delta
mode requires meaningful deltas from the source. OSC retains raw packets,
decoded values or errors, direction, endpoint, and stable ordinals. Every JSONL
line is complete, independent of prior file compression state. See the
[capture journal format](../../recs/doc/session-record-format.md) for precise clock semantics,
recovery, and explicit MIDI-file export.

A complete valid empty recording document follows. The example's journal is
an empty asset solely to keep its hash independently reproducible; migration
outputs instead contain the actual version 3 journal snapshot and its hash.

```toml
format = "recs"
version = 2
kind = "recording"
id = "example-session"
name = "Empty capture"
timebases = []

[[assets]]
id = "journal"
path = "journal.jsonl"
encoding = "recs-session-v3"
byte_length = 0
sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

[body]
state = "sealed"
started_at = "2026-09-04T12:00:00Z"
ended_at = "2026-09-04T12:00:01Z"
observed_duration_seconds = 1.0
journal = "journal"
streams = []
```

## Sequence fields

A sequence has named `timebases` and a body containing `timebase`, `start`
(default zero), `end`, and `events` (default empty). The half-open extent is
explicit even when no events occur. Events are ordered by `(tick, ordinal)`,
with unique ordinals across the sequence. Signed integer ticks allow pre-roll;
every event must fall inside the declared extent.

MIDI records contain raw byte integers. OSC records preserve `data_b64`, an
`in`/`out` direction, and optionally a source time; an undecodable OSC payload
can still be retained. Key records contain `key`, `press`/`release` action,
optional text, modifiers, and a repeat flag. These are stored events, not yet a
universal performance engine. Recs also captures its observed key transitions
through the same event model.

Semantic `trigger`, `release`, and `control_change` records use that same
envelope. Their payload and addressing rules are defined in the
[instrument contract](instrument-format.md#performance-input). A
[portable performance sequence](../conformance/performance.json) demonstrates
preroll controls and overlapping triggers with distinct identities.

```toml
format = "recs"
version = 2
kind = "sequence"
id = "key-example"
name = "One key gesture"

[[timebases]]
id = "milliseconds"

[timebases.rate]
numerator = 1000
denominator = 1

[body]
timebase = "milliseconds"
start = 0
end = 1000

[[body.events]]
kind = "key"
tick = 0
ordinal = 0
key = "a"
action = "press"

[[body.events]]
kind = "key"
tick = 500
ordinal = 1
key = "a"
action = "release"
```

## Explicit version 3 conversion

For a stopped session whose journal paths are relative to its own directory:

```sh
recs session migrate /path/to/session
```

For older journals that include a session-directory prefix relative to the
original recording parent, supply that parent explicitly:

```sh
recs session migrate '/recordings/2026-09-04 15-01-57' --paths-relative-to /recordings
```

The command verifies hashes, decodes every finished audio file, checks native
frame intervals, channels and sample rates, and counts MIDI/OSC events before
writing anything. A count/span discrepancy becomes an explicitly unmapped
fragment and a report entry; corrupt payloads and inconsistent sample rates or
channels still fail. It then creates:

- `recording.toml`, containing paths relative to the session directory;
- `migration/session-record-v3.jsonl`, an exact preserved journal copy;
- `migration/report.json`, with verification totals and limitations.

Existing outputs cause an error. Neither the original journal nor media is
rewritten. Asset paths and resolved symlinks must remain within the session.
The whole session directory can be moved without changing candidate paths.
`verify_recording(document, root)` rechecks the payloads independently of the
production reader.

A malformed final JSON line may be preserved as interrupted evidence, making
the candidate open. Invalid complete records and corruption in the middle are
errors. Unfinished files are listed but never claimed as verified payloads.
Convert each segment of a historical continuation chain separately. The
converter translates its continuation filenames to `recording.toml`, retaining
the relative directory links. It does not migrate other volumes automatically;
all linked documents must exist before reading or exporting the chain.

Historical gaps receive reason `unknown`; wall-clock shutdown time does not
establish trailing sample extent. Each historical audio stream retains its
own native clock. MIDI timestamps already quantized into SMF cannot be made
more precise by conversion. New captures retain native timing and measured clock observations. Fitted
cross-device alignment remains later work; migration cannot recover missing
historical observations.

## Reading, checking, and portable export

```sh
recs session show /path/to/session
recs record check /path/to/session/recording.toml
recs session export /path/to/session/recording.toml /path/to/export
recs session export-midi /path/to/session/recording.toml midi:keys take.mid
```

The checker follows continuations, verifies asset hashes and byte lengths,
decodes audio, and counts events. Open recordings and unresolved audio placement
produce explicit diagnostics. Browsing reports these states without decoding
all audio; its warnings and control markers come from the referenced journal.
`recs explain /path/to/session/session-record.jsonl` still examines operational
evidence directly, including captures that have not finalized.

Export requires sealed documents and verifies every asset before copying.
It includes all linked segments, rewrites common-document continuation paths,
and verifies copied assets. Original journal bytes remain unchanged as evidence.
The result starts at `recording.toml`; additional segments live under `sessions/`.
Moving the exported directory preserves media references and native frame gaps.
Export can preserve unresolved historical recordings, but it does not resolve
their timing. The editor requires sealed, fully mapped selected audio streams.

For a stopped version 4 capture that did not finalize, run
`recs session finalize /path/to/session`. Complete finished fragments are
verified; torn final lines and unfinished files remain explicitly open. Existing
outputs are never replaced. A new capture process has a new audio clock identity;
volume changes within that process retain it. Editing across independent capture
clocks requires an explicit alignment decision.

## Public exports and imported media

Version 2 exposes streams through root `ports`, with an output direction, matching
stream contract and `binding = { stream = "stable-stream-id" }`. An audio binding
may select consecutive zero-based `channels`. Native event exports declare their
physical clock and event kinds; legacy files without native tick positions are
not automatically exported as timed composition sources.

A sealed recording describing imported media may omit `journal`, `started_at`
and `ended_at`. Captured sessions retain their journal and capture timestamps.
This avoids inventing capture history when wrapping a WAV file for composition.
