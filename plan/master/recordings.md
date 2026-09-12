# Recordings, assets, and portable files

## Incomplete

Dense-array streams and general score-dependency packaging remain proposals
for later stages. The current completed profile covers capture journals and
recording metadata, not a general portable package implementation.

## Recording score

A recording contains stream descriptors, clock observations, fragments, gap
records, and asset references. Each stream has a stable ID, source endpoint
identity, semantic type, and native timebase. Fragments declare `asset`,
`asset_start`, native `start`, and `count`; sampled counts mean frames, while
event fragments declare their event count and explicit temporal extent.
Never use the same count field as both event quantity and elapsed time.

Each gap declares its interval and reason, such as silence suppression, input
overflow, disconnected device, or unavailable source. Silence suppression means
an intentional omission under a recorded threshold policy, not exact knowledge
that every sample was zero. Unknown duration remains unknown, with boundary
observations; do not manufacture an exact gap length.

Illustrative recording fragments:

```toml
[[streams]]
id = "desk"
family = "sampled"
schema = "recs.audio"
timebase = "desk-clock"
channels = ["left", "right"]

[[streams.fragments]]
asset = "take-a"
asset_start = 0
start = 0
count = 48000

[[streams.gaps]]
start = 48000
end = 96000
reason = "input_overflow"

[[streams.fragments]]
asset = "take-b"
asset_start = 0
start = 96000
count = 48000
```

With a 48 kHz native clock, this is a three-second timeline containing two
seconds of captured audio. The missing second does not slide the second file
earlier. Alternate encodings of the same interval share an explicit variant
group; they are not overlapping takes to mix together.

## Payload storage

Use TOML for authored definitions. Reuse existing audio codecs and simple
sidecar formats rather than inventing a universal binary container:

| Payload | Initial storage |
| --- | --- |
| Audio samples | WAV/FLAC or another explicitly supported codec, with decoded frame metadata |
| Dense numeric control or pixel arrays | Non-object NPY arrays, with semantic axes, unit, layout, and clock in the recording score |
| Recorded events and raw packets | UTF-8 JSONL with the shared event schema; binary fields use base64 |
| Small authored curves and sequences | Inline typed TOML records |
| Plugin-specific state | Opaque asset with implementation identity and declared encoding |

NPY is a proposed initial array encoding because these projects already use
NumPy; object arrays and pickle loading are excluded. Rotation produces bounded
array fragments rather than a single indefinitely growing array. An exchange
reader needs only the encodings used by its selected streams.

Assets declare decoded shape/rate where applicable. Sealed assets have SHA-256
and byte length so edits cannot silently reuse changed content. A path locates
an asset; its digest identifies those bytes. A re-encoded file has a new digest
even if its decoded samples are identical. Keep source lineage separately.

## A run while it is still happening

Definitions are immutable inputs to a run. Use an append-only JSONL journal for
fragment start/finish, clock observations, gaps, requests/results, operator
decisions, and errors. This extends the useful pattern of the existing Recs
session record rather than rewriting TOML on every audio block.

Only a finished fragment with verified metadata becomes a sealed asset.
An interrupted fragment remains partial. Recovery accepts complete journal
records up to a torn final line and reports that line; corrupt interior records
remain errors. Finalization produces a recording score and preserves the
journal as provenance. A recording that is still open is explicitly marked open
and exposes only verified completed fragments to an ordinary offline reader.

For recording across removable volumes, preserve stable stream IDs and explicit
continuation links. Consolidated portable export collects the selected fragments
and preserves the original timeline, including gaps and continuation history.

## Portable package

Use an ordinary directory containing a root TOML score, dependent scores,
assets, and run journals. References must remain inside the exported root after
path and symlink resolution. Import and authoring may select external local
files, but portable export copies the dependency closure and rewrites paths.
Do not embed credentials, machine sockets, or transient in-memory IDs.

Keep live endpoint requirements in the package as logical interfaces. A future
microphone feed has no asset hash; a completed capture replacing it does. A
missing dependency is an actionable validation error and not permission to
search the network for a vaguely similar replacement.

## Change from today

The original `SessionHeader` version 3, `FileRecord`, and `EventRecord` in
`recs/ui/session_record.py` already capture stream identity, file lifecycle,
quantities, and diagnostic events. Replace their optional audio/MIDI/OSC field
mixture with typed stream and observation records. Keep the journal write and
recovery behavior where suitable. Replace `SOURCE:TRACK[:OFFSET]` parsing in
`recs/edit/record.py` with structured stream and channel references.

`AudioFragment` and `ResolvedSource` remain useful runtime concepts, but resolved
paths, loaded buffers, and estimated clocks must not become the portable source
definition. Extend the existing session export workflow rather than adding a
second export path with different containment and gap semantics.

## Implemented stage 2 profile

Current captures use typed version 4 journal records, native MIDI/OSC/key JSONL,
measured clock observations, and explicit audio gap evidence. See the normative
[recording score](../../doc/recording-format.md) and
[capture journal](../../doc/session-record-format.md) profiles. Dense arrays and
general score dependency packaging above remain proposals for later stages.
