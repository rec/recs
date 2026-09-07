# Session Record Format

## Purpose

A Recs session journal is the append-only lifecycle history for one recording
session. On completion, it supplies evidence for the canonical
[`recording.toml` content index](recording-format.md). Browsing, checking,
export, and editing use that common document; diagnostics and recovery still
inspect the journal, including while a recording is incomplete.

The record is named `session-record.jsonl`. It is stored at the root of a
session directory beside the media directory tree:

```text
2026-09-01 20-15-15/
  session-record.jsonl
  audio/
    X18-1-2.flac
  midi/
    Launchkey-20260901-201515.mid
  osc/
    X18.jsonl
```

Audio samples, MIDI messages, and OSC packets are stored in referenced data
files, not embedded in session-record entries. Counts and summaries of those
quantities may appear in file entries. Key presses and releases, marks, source
state, and other low-volume operational observations are lifecycle entries in
the record itself.

Referenced paths are relative to the directory containing
`session-record.jsonl`. They MAY use media subdirectories, but MUST NOT be
absolute or escape the session directory with `..`.

## Encoding

The session record is UTF-8 JSON Lines. Each non-empty line is one JSON object.
Entries are written in observation order. Readers MUST use each entry's time
fields rather than treating line order as exact chronological order.

Writers append complete lines and flush them promptly. The current reader keeps
valid entries and reports every malformed line, identifying a malformed last
line as `truncated final line`. The validator treats that report as an error.
Unknown string-valued lifecycle entry types are retained as events; unknown
fields within a known entry shape are rejected.

The first entry MUST be a header. A normally completed record MUST end with a
footer. An absent footer identifies an unfinished session and does not make
earlier complete entries unusable.

## Time

Wall-clock times use RFC 3339 UTC strings ending in `Z`. Writers SHOULD retain
the greatest precision supplied by their clock and MUST NOT write local times
or UTC offsets. For example:

```json
{"timestamp":"2026-09-01T18:15:15.123456789Z"}
```

The header's `started_at` is the session's wall-clock origin. Lifecycle entries
use `timestamp`; the footer uses `ended_at`.

The session record's wall-clock timestamps locate and correlate files. Exact
sample, message, packet, or frame timing belongs in each data file. A file
format without an intrinsic time representation MUST define one in its schema.
Integer counters and rational rates SHOULD be used there instead of floating
point seconds. This permits, for example, an audio sample position at 44,100
samples per second or a MIDI tick at 960 ticks per beat without rounding it to
nanoseconds.

When a source clock is not the system wall clock, its file entry MUST identify
the timing source. A data format MAY include both source-clock and wall-clock
observations so later tools can estimate drift or clock discontinuities.

## Header

Format version 3 begins with:

```json
{"type":"header","version":3,"session_id":"4b21821a-c52a-47d2-8f60-94e482db3770","started_at":"2026-09-01T18:15:15.123Z"}
```

Required fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `type` | string | Always `header` |
| `version` | integer | Session record format version, currently `3` |
| `started_at` | string | RFC 3339 UTC session origin |

Optional fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `session_id` | string | UUID shared by disk continuations; current writers always provide it |
| `continued_from` | string | Relative path to the preceding session record |
| `application` | object | Writer name and version |
| `metadata` | object | User-supplied session metadata |

## File Entries

Every data file has one `file_started` entry and, when it closes normally, one
`file_finished` entry. Both identify the same `stream_id` and `path`.

```json
{"type":"file_started","timestamp":"2026-09-01T18:15:15.123Z","stream_id":"audio:x18:1-2","media_type":"audio","path":"audio/X18-1-2.flac","format":"flac","source":"X18","track_name":"room","source_channels":[1,2],"channels":2,"sample_rate":48000,"bit_depth":16}
```

```json
{"type":"file_finished","timestamp":"2026-09-01T19:15:15.123Z","stream_id":"audio:x18:1-2","media_type":"audio","path":"audio/X18-1-2.flac","format":"flac","source":"X18","frame_count":172800000,"quantity_count":172800000}
```

Required fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `type` | string | `file_started` or `file_finished` |
| `timestamp` | string | Wall-clock observation time |
| `stream_id` | string | Stable identity across files and disk switches |
| `media_type` | string | Built-in or user-defined medium |
| `path` | string | Data-file path relative to the session record |
| `format` | string | File format or schema identifier |

Optional fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `source` | string | Human-readable source or device identity |
| `track_name` | string | Configured or canonical logical track name |
| `source_channels` | array of integers | Exact source channels represented, in file order |
| `frame_count` | integer | Source timeline frame at file start or finish, when applicable |
| `channels` | integer | Number of audio channels in the file |
| `sample_rate` | integer | Audio sample rate in frames per second |
| `bit_depth` | integer | Stored audio bits per sample |
| `quantity_count` | integer | Samples, messages, packets, or frames represented |
| `audio_spans` | array of objects | Finished audio's native `start`, payload `asset_start`, and stored frame `count` for each contiguous span |
| `timing_source` | string | Clock used within the data file |
| `midi_port` | string | MIDI input port name |
| `osc_node` | string | Configured OSC node name |
| `inbound_count` | integer | Received OSC packet count |
| `outbound_count` | integer | Sent OSC packet count |
| `decode_error_count` | integer | OSC packet decode-error count |
| `metadata` | object | Media-specific declarative metadata |

`quantity_count` is a summary, not embedded quantity data. Its unit is defined
by `media_type` or by the user-defined schema.

A stream split by silence, size, duration, disconnection, or disk replacement
keeps the same `stream_id` and receives a new path. A source with several
logical outputs uses a distinct stream ID for each output.

## Built-In Media Types

### Audio

`media_type` is `audio`. `quantity_count` counts sample frames. Audio entries
use `track_name` for the configured or canonical logical track and
`source_channels` for its exact ordered hardware channels. `channels` is the
number of channels in the file; `sample_rate` and `bit_depth` describe its PCM
representation. Metadata MAY include speaker positions and codec settings.
Samples remain in the audio file. Finished audio records include `audio_spans`
to locate samples precisely after silence suppression: payload offsets cover
the file consecutively while native positions can have gaps. `quantity_count`
is the sum of stored span counts. Older journals computed it from native
endpoints, which can disagree with stored frames; explicit conversion retains
that discrepancy as unresolved placement rather than guessing silence locations.

### MIDI

`media_type` is `midi`. `quantity_count` counts MIDI messages. Metadata SHOULD
include the port name and timing source. Recs writes type-0 Standard MIDI Files
at 960 ticks per beat with an initial 120 BPM tempo event and delta-timed
messages.

### OSC

`media_type` is `osc`. `quantity_count` counts packets. Current entries use the
top-level `osc_node`, `inbound_count`, `outbound_count`, and
`decode_error_count` fields. The OSC data file contains packet payloads,
directions, endpoints, and packet times.

## User-Defined Media Types

The `FileRecord` model accepts any string for `media_type` and `format`, so
applications can index additional file-backed media. A user-defined
`media_type` should use a collision-resistant reverse-domain name, such as
`org.example.motion-capture`. The optional `metadata` object contains
declarative parameters needed to interpret that file.

Extensions MUST keep quantity data in the referenced file. They MUST NOT add
top-level fields beyond those accepted by `FileRecord`; additional declarative
values belong in `metadata`. This keeps generic readers able to index, move,
validate, and recover files without understanding every medium.

## Lifecycle Entries

The record may contain source discovery and failure, audio pause and resume,
configuration changes, warnings, marks, key transitions, disk pressure, disk
replacement, calibration, and session-continuation events. These entries
describe the recording process; they do not carry media quantities.

Every lifecycle entry has `type` and `timestamp`. `EventRecord` provides the
optional top-level fields used by current writers, including `source`, `track`,
`key`, `label`, `address`, `value`, frame and drop counts, queue and write
timings, paths, disk values, continuation links, configuration revision, and
MIDI or OSC source names. Less common structured values may use `metadata`:

```json
{"type":"source_failed","timestamp":"2026-09-01T18:20:00.000Z","source":"Launchkey","reason":"device disconnected"}
```

A warning uses its own entry shape with `type` set to `warning`, a required
string `message`, and optional `first_timestamp` and repeat `count`.

## Continuation

When recording moves to another disk, Recs closes the current files and session
record, then creates a new session directory and `session-record.jsonl`. The new
header keeps the same `session_id` and uses `continued_from` to identify the old
record. Before its footer, the old record contains a
`disk_switch_continued_at` lifecycle entry naming the new record.

The `new_session` protocol command uses the same reciprocal record links but
assigns a new `session_id`. Its old record contains a `session_continued_at`
entry naming the new record. The new record's `continued_from` points back to
the old record.

Continuation paths are relative when both records are addressable from a common
filesystem tree. A record copied without its predecessor remains readable, but
`recs record check` reports the missing linked record.

## Footer

A clean shutdown appends:

```json
{"type":"footer","ended_at":"2026-09-01T19:15:15.123Z","duration_seconds":3600.0}
```

`type` and `ended_at` are required. `duration_seconds` is an informational
summary measured by the writer. Readers use the timestamps and data-file timing
for precise analysis.

## Validation

A conforming record should satisfy the rules above. The current
`recs record check` command checks:

- a readable version-3 header;
- a footer with a non-negative duration;
- relative paths contained by the session directory;
- a matching finish entry for every started file;
- existing referenced files;
- plausible audio file sizes when frame and PCM metadata are available;
- non-empty MIDI files when a finished entry reports messages;
- nondecreasing frame counts for each stream;
- existing continuation targets and a backlink for each forward continuation event;
- non-negative quantity counts.

Pydantic validation rejects unsupported header versions and unknown fields in
the defined entry models. `recs record check` reports a missing footer as an
unfinished session.
