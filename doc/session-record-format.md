# Session Record Format

## Purpose

A Recs session record is the canonical index and lifecycle history for one
recording session. It can describe any time-based medium without embedding the
medium's quantity data in the record itself.

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

Samples, MIDI messages, OSC packets, keystrokes, DMX frames, LED frames, and
other quantity data MUST be stored in referenced data files. They MUST NOT be
embedded as session record entries. Counts and summaries of those quantities
MAY appear as metadata.

Referenced paths are relative to the directory containing
`session-record.jsonl`. They MAY use media subdirectories, but MUST NOT be
absolute or escape the session directory with `..`.

## Encoding

The session record is UTF-8 JSON Lines. Each non-empty line is one JSON object.
Entries are written in observation order. Readers MUST use each entry's time
fields rather than treating line order as exact chronological order.

Writers append complete lines and flush them promptly. A reader MAY ignore one
truncated final line after an abnormal exit. Invalid earlier lines are errors.
Unknown top-level entry types are errors for the format version declared by the
header.

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
| `session_id` | string | UUID shared by continuation records |
| `started_at` | string | RFC 3339 UTC session origin |

Optional fields:

| Field | Type | Meaning |
| --- | --- | --- |
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
{"type":"file_finished","timestamp":"2026-09-01T19:15:15.123Z","stream_id":"audio:x18:1-2","media_type":"audio","path":"audio/X18-1-2.flac","format":"flac","source":"X18","quantity_count":172800000}
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
| `quantity_count` | integer | Samples, messages, packets, or frames represented |
| `timing_source` | string | Clock used within the data file |
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
Exact sample timing and samples remain in the audio file.

### MIDI

`media_type` is `midi`. `quantity_count` counts MIDI messages. Metadata SHOULD
include the port name and timing source. The MIDI file contains messages,
ticks-per-beat, tempo changes, and event timing.

### OSC

`media_type` is `osc`. `quantity_count` counts packets. Metadata SHOULD name the
OSC node and MAY include inbound, outbound, and decode-error counts. The OSC
data file contains packet payloads, directions, endpoints, and packet times.

### Keystrokes

`media_type` is `keystrokes`. A referenced file contains key transitions and
their times. Metadata MAY identify the keyboard, application scope, key naming
scheme, and whether releases or repeats are retained.

### DMX

`media_type` is `dmx`. A referenced file contains timed frames or changes.
Metadata SHOULD identify the universe or transport, channel count, value width,
and whether the file stores complete frames or deltas.

### LED collections

`media_type` is `led`. A referenced file contains timed component values for a
collection of lights. Metadata MUST declare the light count and ordered
component names. Component names are an open list, so layouts such as `W`,
`RG`, `RGB`, `RGBW`, and `RGBWV` are represented without format changes:

```json
{"lights":300,"components":["r","g","b","w","uv"],"value_width":8}
```

## User-Defined Media Types

Applications MAY define additional media types. A user-defined `media_type`
MUST use a collision-resistant reverse-domain name, such as
`org.example.motion-capture`. Its `format` MUST identify the data-file encoding
or schema. The optional `metadata` object contains declarative parameters needed
to interpret that file.

Extensions MUST keep quantity data in the referenced file. They MUST NOT add
top-level fields to session record entries. This keeps generic readers able to
index, move, validate, and recover files without understanding every medium.

## Lifecycle Entries

The record MAY contain metadata and lifecycle events such as source discovery,
source failure, pause or resume, configuration changes, warnings, marks, disk
pressure, and disk replacement. These entries describe the recording process;
they do not carry media quantities.

Every lifecycle entry has `type` and `timestamp`. Event-specific values belong
under `metadata`:

```json
{"type":"source_failed","timestamp":"2026-09-01T18:20:00.000Z","metadata":{"stream_id":"midi:launchkey","message":"device disconnected"}}
```

A warning has the same form with `type` set to `warning` and a required string
`message`.

## Continuation

When recording moves to another disk, Recs closes the current files and session
record, then creates a new session directory and `session-record.jsonl`. The new
header keeps the same `session_id` and uses `continued_from` to identify the old
record. Before its footer, the old record contains a
`disk_switch_continued_at` lifecycle entry naming the new record.

Continuation paths are relative when both records are addressable from a common
filesystem tree. A record copied without its predecessor remains readable; the
missing continuation is a validation warning rather than corruption of the
local entries.

## Footer

A clean shutdown appends:

```json
{"type":"footer","ended_at":"2026-09-01T19:15:15.123Z","duration_seconds":3600.0}
```

`type` and `ended_at` are required. `duration_seconds` is an informational
summary measured by the writer. Readers use the timestamps and data-file timing
for precise analysis.

## Validation

A conforming validator checks at least:

- one version-3 header as the first complete entry;
- at most one footer, as the final complete entry;
- valid UTC timestamps;
- relative paths contained by the session directory;
- one matching start entry for every finished file;
- existing referenced files;
- stable `media_type`, `format`, and `stream_id` for each path;
- non-negative quantity counts;
- valid continuation links when their targets are available;
- no quantity payloads embedded in record entries.

Readers MUST reject unsupported versions rather than guessing their meaning.
