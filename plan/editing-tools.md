# Editing Tools

## Scope

Implement a built-in `recs edit` command family for transforming media described
by a Recs session record into a new Recs session:

```text
recs edit split [RECORD] ...
recs edit stitch [RECORD] ...
recs edit clip [RECORD] --start START --end END ...
recs edit NAME [RECORD] ...
recs edit PATH.toml [RECORD] ...
```

Every command accepts an optional positional session record. When omitted,
Recs selects the most recently modified `session-record.jsonl` below the current
directory. It never edits the source record or source recordings.

Every successful invocation emits exactly one new session directory, regardless
of how many files it generates. That directory contains a new
`session-record.jsonl`, the generated files in their media subdirectories, and
the fully resolved edit TOML. An edit is therefore a session-to-session
transformation, not a file-producing command with a separate provenance format.

```text
concert-edit/
  session-record.jsonl
  edit.toml
  audio/
    concert-mix.flac
    voice-stem.flac
```

`~/code/fmix` is superseded, not imported or treated as a compatibility target.
Its ordered `[[edit_points]]` are too narrow to represent general editing:
they describe which inputs are audible at successive times, but not reusable
clips, independent source and destination positions, overlapping material,
track routing, buses, or multiple outputs. Recs instead uses a declarative
arrangement graph as its durable edit model.

Every edit subcommand is backed by one TOML file containing partial values for
that model. The packaged `clip.toml`, `stitch.toml`, `split.toml`, and `mix.toml`
files provide the built-ins. Users add named edit commands by adding TOML files,
without writing or loading Python plugins. Shared schema, timeline, and
rendering code remains in Recs; a TOML command can combine existing capabilities
but cannot introduce executable code or a new DSP primitive.

## Design Principles

The canonical document describes the desired arrangement, not a sequence of
destructive editing commands. Rendering the same document against the same
record must produce the same timeline and routing decisions.

- All timeline positions and source positions are integer sample frames.
- One declared sample rate defines the edit timebase.
- Stable IDs connect sources, tracks, clips, buses, automation, and outputs.
- Clips place source intervals independently on an output timeline.
- Tracks and buses define channel widths and explicit routing.
- Automation controls parameters over time without special edit-point syntax.
- Outputs select tracks or buses and choose encoding separately from editing.
- One edit invocation produces one new session directory and session record.
- Each edit declares the media types it understands; other media is omitted.
- The complete schema and partial command recipes are the same data model.
- Validation, bounded rendering, and encoding remain separate concerns.

Human-readable durations remain available on the CLI. Recs converts them to
frames before writing canonical TOML. The durable file never depends on decimal
seconds, musical tempo, filesystem timestamps, or floating-point time.

## Session Transformation Model

An edit implementation declares the `media_type` values it handles. The initial
`clip`, `stitch`, `split`, and `mix` implementations handle only `audio`. They
select audio entries from each input session record and omit MIDI, OSC, and all
other media from the output session. They do not copy unsupported files, create
placeholder entries for them, or carry their lifecycle events into the new
record.

Omission is intentional, not an error. An input session may contain any mixture
of media. The session record itself must be structurally readable, but an audio
edit neither opens nor validates referenced MIDI, OSC, or user-defined media
files. A future MIDI or OSC edit follows the same rule for its own declared
media types. An edit that combines or passes through several media types must
declare and implement that behavior explicitly.

Each invocation creates a new session identity. Its record is not a continuation
of any input record: `continued_from` is reserved for one recording session
moving between disks. Instead, the output record contains an edit lifecycle
entry naming the canonical `edit.toml`, input session records and session IDs,
selected media types, and source selectors. Its `file_started` and
`file_finished` entries describe only files generated in the output session.

## Audio Input Model

A source refers to one `session-record.jsonl` and selects one logical channel or
one configured multichannel track from it. Matching audio `file_started` and
`file_finished` entries provide the relative path, stream ID, source, track
name, ordered source channels, file channel count, sample rate, bit depth,
starting and ending `frame_count`, and `quantity_count`. The editor resolves
segmented files, reconnects, and known gaps behind each source ID.

Record selectors use this stable identity:

```text
SOURCE:TRACK[:OFFSET]
```

Omitting `OFFSET` selects the complete configured track. Supplying an offset,
starting at one, selects one logical channel. A source records its channel width
after resolution so later tracks, routes, and clips can be validated without
reopening media files.

File ranges are positioned by record frame counts, not wall-clock timestamps.
A known gap in a source is rendered as zero-valued samples. An overlap between
distinct source files for the same logical channel is an error; the editor must
not silently sum or choose one file.

Recs can record more than one encoded copy of a track. Files with identical
source-frame ranges are variants, not separate inputs. A source can select an
input format explicitly. Otherwise the editor uses this preference order:

```text
wav, rf64, flac, ogg, mp3, raw
```

If no single variant covers a range, resolution stops with the conflicting
records listed. Multiple encodings never duplicate the same recorded audio in
the arrangement.

All selected sources must initially have the edit's sample rate. Mixed rates
fail before the output session directory is created. Streaming resampling is a
possible later primitive, but it must be explicit in the edit rather than
silently treating frames from different rates as interchangeable.

## General Edit TOML Format

TOML serializes the durable edit model. A complete example is:

```toml
schema_version = 1
sample_rate = 48000

[[sources]]
id = "ben"
record = "../session-record.jsonl"
channel = "X18:3"
input_format = "flac"

[[sources]]
id = "room"
record = "../session-record.jsonl"
channel = "X18:5"

[[tracks]]
id = "voice"
channels = 2

[[tracks]]
id = "ambience"
channels = 2

[[buses]]
id = "master"
channels = 2

[[clips]]
id = "opening-voice"
source = "ben"
track = "voice"
source_start = 2880000
source_end = 5904000
timeline_start = 0

[[clips]]
id = "later-voice"
source = "ben"
track = "voice"
source_start = 7200000
source_end = 10176000
timeline_start = 3024000

[[clips]]
id = "room-bed"
source = "room"
track = "ambience"
source_start = 2880000
source_end = 8832000
timeline_start = 0

[[routes]]
source = "voice"
destination = "master"
gain = 1.0

[[routes]]
source = "ambience"
destination = "master"
gain = 0.5

[[automation]]
target = "route:ambience->master:gain"
interpolation = "linear"
points = [
  { frame = 0, value = 0.0 },
  { frame = 48000, value = 0.5 },
  { frame = 5904000, value = 0.5 },
  { frame = 5952000, value = 0.0 },
]

[[outputs]]
id = "mix"
source = "master"
path = "audio/concert-mix.flac"
format = "flac"
subtype = "pcm_24"

[[outputs]]
id = "voice-stem"
source = "voice"
path = "audio/voice.flac"
format = "flac"
subtype = "pcm_24"
```

`schema_version` and `sample_rate` are required in a complete edit. Unknown
versions, fields, IDs, target parameters, and interpolation modes fail.
Paths in an explicit edit file are relative to that file; paths supplied on the
command line are relative to the current directory.

### Sources

Each `[[sources]]` entry has a unique `id`, a record path, and one record
channel selector. It may constrain `input_format`. A complete track selector
creates a source with that track's width; an offset selector creates a mono
source. Multiple source IDs may select the same recorded material when the
arrangement intentionally reuses it.

The record path belongs to the source rather than the whole edit. This allows
one arrangement to combine independently recorded sessions without inventing a
second input format. All records must still resolve to the declared edit
sample rate and have unambiguous frame origins.

### Tracks And Buses

Each `[[tracks]]` entry declares a unique `id` and fixed channel count. Clips
place material directly on tracks. Overlapping clips on one track are summed;
this is an explicit arrangement decision, unlike overlapping record fragments
inside one source, which remain an error.

Each `[[buses]]` entry also has a unique ID and channel count. Buses receive
routes from tracks or other buses. Acyclic routing is required. A route's source
and destination widths must match in the first implementation; there is no
implicit mono duplication, downmix, or channel reshaping.

Each `[[routes]]` entry names a track or bus as `source`, a bus as
`destination`, and an initial linear `gain`. Routing is explicit even for a
simple mix. This makes stems, submixes, and multiple masters ordinary views of
one arrangement instead of separate edit types.

### Clips

Each `[[clips]]` entry maps one half-open source interval onto one track:

```text
[source_start, source_end) ->
[timeline_start, timeline_start + source_end - source_start)
```

All three positions are non-negative integer frames and `source_end` must be
greater than `source_start`. The source and track channel widths must match.
Clips can reuse a source interval, overlap other clips, leave timeline gaps,
appear in any order in TOML, and place recorded material in a different order
from the source. A clip does not modify its source.

Clip IDs are required because automation and provenance may refer to one clip.
The canonical file sorts no arrays: TOML order is retained for readability, but
IDs and frame positions, not declaration order, determine rendering.

### Automation

Automation replaces fmix's special-purpose `[[edit_points]]`. Each
`[[automation]]` entry names one typed parameter target, an interpolation mode,
and frame/value points. Initially supported targets are:

```text
clip:CLIP_ID:gain
route:SOURCE_ID->DESTINATION_ID:gain
bus:BUS_ID:gain
```

Initial interpolation modes are `hold`, `linear`, and `equal_power`. Points
must have strictly increasing frames. Before the first point, the parameter's
declared value applies. After the last point, its final value remains active.
Two automation entries cannot control the same target.

A fade is ordinary gain automation. A crossfade is overlapping clips or routes
with complementary automation. Gain changes, muting, cuts, and rearrangement
therefore share one timeline model rather than requiring different edit-point
meanings. Curves are evaluated a block at a time without allocating arrays for
the complete fade or recording.

### Outputs

Each `[[outputs]]` entry selects one track or bus and specifies a path, format,
and optional subtype. The path is relative to the new session directory and
must remain inside the subdirectory for its media type, initially `audio/`.
Multiple outputs render a master, submixes, and stems as separate files in the
same output session. Encoding options do not change timeline or routing
semantics.

The output session directory is an invocation-level destination, not one
`[[outputs]]` entry per top-level result. It is supplied or derived by the CLI
before rendering and must not already exist. Recs never merges an edit into an
existing session, so per-file overwrite settings are unnecessary. Duplicate or
colliding output paths fail during validation before the directory is created.

An output starts at frame zero and ends at the final non-silent extent of its
selected graph unless an explicit `start` or `end` frame is present. These
bounds crop the rendered arrangement; they do not alter source or clip frame
coordinates. A requested interval is authoritative, so known empty regions are
written as silence rather than trimmed.

Peak processing belongs to an output, not the arrangement. Each output may set
`normalize` to `none`, `limit`, or `normalize`, and a final linear `gain`.
`limit` scales only when the peak exceeds full scale; `normalize` always scales
the peak to full scale. Both require a bounded analysis pass followed by a
render pass.

## Complete Edits And Partial Recipes

The same versioned data classes parse complete edits and partial named-command
TOMLs. A partial recipe may omit values supplied by another recipe, the
record, command-line options, or generated command behavior. A reserved
`_command` table contains CLI metadata rather than edit data.

`extends` names another command TOML and applies its values first. Extension
chains are allowed, but cycles and duplicate command names are errors. Scalars
replace inherited scalars, tables merge by key, and lists such as `sources`,
`tracks`, `clips`, `routes`, `automation`, and `outputs` replace inherited lists
in full. There is no element-by-element list merge.

Recs discovers commands in these locations:

1. An explicit path passed as the command, such as `recs edit ./radio.toml`.
2. `.recs/edit/NAME.toml` below the current project.
3. `~/.config/recs/edit/NAME.toml`, or the corresponding platform config
   directory on Windows.
4. Packaged files in `recs/edit/commands/`.

Named files must not collide across discovery locations; Recs reports every
conflicting path instead of silently shadowing one command. An explicit path is
unambiguous and is exempt from this check.

A user recipe can set output defaults or provide a reusable arrangement
template:

```toml
extends = "clip"

[[outputs]]
id = "main"
format = "flac"
subtype = "pcm_24"
normalize = "none"

[_command]
help = "Create a 24-bit stereo extract"
```

It then appears as `recs edit podcast`. Adding an operation such as noise
reduction still requires implementing and testing a typed primitive in Recs,
adding it to the versioned edit schema, and exposing it through TOML. Recs
never imports Python from command directories or permits shell commands in edit
TOML.

## Built-In Commands

The built-ins are projections onto the general model, not independent renderer
paths.

### `recs edit clip`

`clip` selects record channels and one interval. It generates one source and
track per selected configured track, one clip per source, and one output for the
result. CLI durations are converted to source and timeline frames. No gain,
normalization, or fades are introduced unless the recipe requests them.

### `recs edit stitch`

`stitch` generates consecutive clips from selected source intervals. Each
clip's `timeline_start` is the end of the preceding clip, so disjoint or
reordered source intervals become one continuous arrangement. With no explicit
intervals, it places the complete record timeline at frame zero and preserves
known gaps as silence.

### `recs edit split`

`split` creates one output per selected logical mono channel or configured
multichannel track. All outputs refer to aligned tracks in the same arrangement,
so they share a frame-zero origin and can be recombined without guessing their
timing.

### `recs edit mix`

`mix` creates tracks, a master bus, explicit routes, and one master output.
Command options can generate route-gain automation and overlapping clips for
crossfades. It uses no fmix-style input aliases or edit-point state. The result
is canonical TOML that can be extended with additional tracks, buses, clips,
routes, automation, and outputs.

## Common Command Behaviour

After resolving command TOML, Recs parses every command through one
Pydantic/Tyro `EditCli` data class. This keeps dynamically discovered commands
on the same validated CLI instead of generating Python classes or functions for
each file. Effective values are applied in this order:

```text
schema defaults
extended command TOML files
selected named or explicit-path command TOML
positional record
command-line options
generated command arrangement
```

Generated command data fills absent values and converts concise CLI selections
into explicit sources, tracks, clips, routes, automation, and outputs. It must
not override an explicit complete edit silently.

Before writing audio, commands print a concise plan: command and command-file
path, source records, selected media types and channels, sample rate, timeline
bounds, tracks, buses, output session directory, output formats, and output
paths.

Every successful run writes a canonical, fully resolved `edit.toml` at the root
of its new session directory. It includes `schema_version` and all effective
values, omits `extends` and `_command`, converts all time values to frames, and
rewrites input record paths relative to the output directory when possible. It
therefore keeps the same meaning if an installed command recipe later changes
or disappears.

The adjacent `session-record.jsonl` is the sole record of what was produced.
Its header has a new session ID and identifies Recs edit as the application. An
`edit_started` lifecycle entry records the canonical edit path and resolved
facts that are not duplicated in that file: source session IDs, selected source
files, gaps rendered as silence, and computed output ranges. Each generated file
receives matching `file_started` and `file_finished` entries with a path relative
to the new session record. A clean run appends a footer. No separate
`edit-record.jsonl` is created, and no input session record is modified.

## Output Channel Limits

An output selects one track or bus with a known width. If its format cannot
contain that width, validation fails. The arrangement must explicitly create
separate tracks, buses, or outputs when channel partitioning is desired; the
encoder does not silently rewrite the edit graph.

The initial capacity table is explicit:

| Format | Channels per output file |
| --- | ---: |
| `mp3` | 2 |
| `flac` | 8 |
| `wav`, `rf64`, `ogg`, `raw` | subject to the active `soundfile` backend |

The output writer validates channel count and subtype with `soundfile` before
rendering. A backend rejection is a clear error, not a partial output.

## Rendering Architecture

```text
recs/edit/
  cli.py          Edit dispatcher and shared Pydantic/Tyro command data class
  schema.py       versioned complete and partial edit data classes
  commands.py     command discovery, inheritance, merging, and generation
  commands/
    clip.toml
    stitch.toml
    split.toml
    mix.toml
  record.py     resolve records, selectors, files, variants, and gaps
  graph.py        validate IDs, channel widths, routing, and timeline extents
  automation.py   typed targets and bounded curve evaluation
  render.py       bounded source placement, summing, routing, and analysis
  output.py       encoding and contained media-file naming
  session.py      output directory, canonical TOML, and session record lifecycle
```

`schema.py` owns `EditSpec`, the durable TOML data, and `EditCli`, the uniform
command-line overlay. `commands.py` reads TOML with `tomlkit`, validates the
reserved `_command` table separately, resolves `extends`, and generates a fully
explicit `EditSpec`. Command files contain data only.

`record.py` parses each input record structurally, then exposes entries selected
by the edit's declared media types. For selected audio, it resolves each path
relative to its record and requires it to remain under that record directory.
It validates matching started/finished entries, source-frame ordering, file
existence, and audio metadata before rendering. It does not open or validate
files belonging only to omitted media types.

`graph.py` is format-independent. It validates source, track, clip, route, bus,
automation, and output references; rejects routing cycles and width mismatches;
and computes output extents. It performs no filesystem or audio I/O.

`render.py` reads source material, places clips, sums overlaps, evaluates
automation, and routes tracks through buses in bounded blocks. It never creates
one NumPy array covering an entire recording. It opens output files only after
all validation succeeds and closes all outputs on an ordinary error.

`output.py` owns output-path collision checks, format validation, and encoding.
`session.py` creates the destination only after validation, writes the new
session record and canonical edit TOML, and records generated-file lifecycle
and edit provenance. Arrangement logic does not belong in either module.

Wire `recs edit` in `recs/__main__.py` beside the existing `record`,
`session`, and `explain` command families. It must not start the recorder or
contact the daemon.

## Failure Handling

- Unknown schema versions, fields, IDs, parameters, interpolation modes,
  inheritance cycles, duplicate command names, and invalid partial-value merges
  fail before record or audio I/O.
- A command file cannot name a Python module, executable, or shell command.
- Missing, unreadable, or structurally invalid session records fail before
  output creation. An audio edit with no finished audio entries also fails.
- Files and lifecycle entries for media types unsupported by the selected edit
  are omitted without being copied, opened, or validated.
- Missing input files fail with the source ID and frame range. Silence is used
  only for known record gaps and empty arrangement regions.
- Different sample rates, ambiguous variants, overlapping files within one
  record source, routing cycles, channel-width mismatches, and incompatible
  output formats or subtypes fail explicitly.
- An existing output session directory and duplicate or escaping output paths
  fail before any output is created.
- After output creation, a write failure leaves the new session record without a
  footer. It contains `file_finished` entries only for completed files and a
  warning when that can be appended safely. Completed and partial files remain
  available for inspection or recovery.
- No command modifies source media, source records, configuration, or
  `~/code/fmix`.

## Tests

Use 48 kHz WAV fixtures of at least one second for all digital-audio regression
tests. Test generated audio, canonical edits, and session records, not private
renderer methods.

1. Parse complete and partial edit TOML; reject unknown versions and fields.
2. Discover packaged, project, user, and explicit-path commands; reject name
   collisions, extension cycles, and executable/plugin fields.
3. Verify scalar, table, and whole-list merge rules and CLI precedence, then
   compare emitted canonical TOML with the fully resolved edit.
4. Resolve a mixed-media session for an audio edit; verify that audio is
   selected while MIDI, OSC, user-defined files, and their lifecycle events are
   neither opened nor copied into the output session.
5. Resolve multiple records and selectors, including mono offsets, stereo
   tracks, segmented files, known gaps, and parallel output variants.
6. Reject ambiguous variants, mixed sample rates, overlapping source files,
   missing files, and selectors with no unique match.
7. Validate IDs, clip intervals, channel widths, routing cycles, automation
   targets, strictly ordered points, and output bounds.
8. Render a clip with discontinuous source fragments and verify sample-exact
   silence in gaps and exact source-to-timeline placement.
9. Render consecutive, reordered, reused, and overlapping clips and verify
   summing and frame-exact arrangement extents.
10. Route tracks through one or more buses and produce a master plus aligned
   stems from one edit.
11. Render hold, linear, and equal-power gain automation, including a crossfade
    made from overlapping clips and complementary curves.
12. Verify bounded two-pass limiting and normalization for individual outputs.
13. Reject unsupported channel counts, incompatible subtypes, bad output bounds,
    an existing destination session, and duplicate or escaping paths before
    creating the output directory.
14. Verify every successful command creates one session directory containing a
    new session ID, `edit.toml`, one `session-record.jsonl`, matching lifecycle
    entries for every generated file, and a footer. Verify multiple split or
    stem files remain members of that one session.
15. Interrupt rendering and verify the incomplete output record accurately
    names completed and started files and has no footer.
16. Verify bounded rendering with a long fixture or instrumented block reader;
    the implementation must not read a complete file into one array.
17. Verify `clip`, `stitch`, `split`, and `mix` generate canonical arrangements
    and use the same renderer as an explicit edit TOML.
18. Run manual checks with actual Recs sessions containing silence-induced gaps,
    stereo tracks, an 18-channel arrangement, overlapping clips, stems, and a
    crossfade. Import results into the target DAW and confirm channel order,
    alignment, and audible transitions.

## Implementation Order

1. Implement versioned complete and partial data classes for sources, tracks,
   buses, clips, routes, automation, and outputs, including canonical TOML.
2. Add exact merge and inheritance rules, packaged command recipes, safe command
   discovery, and the uniform Pydantic/Tyro dispatcher.
3. Implement structural session-record input parsing, declared media-type
   selection, audio selectors, source-file variant selection, gap descriptions,
   and sample-rate validation.
4. Implement graph validation for IDs, intervals, widths, routing cycles,
   automation targets, and output extents.
5. Implement creation of a new output session directory, canonical `edit.toml`,
   and session-record lifecycle around one bounded 48 kHz WAV output. Expose
   this path through generated `clip` and `stitch` edits.
6. Add buses, routes, block-wise gain automation, and generated `mix` edits.
7. Add multiple files within one output session and generated `split` edits,
   recording every file and edit provenance in the unified session record.
8. Add bounded output gain, limiting, normalization, and equal-power curves.
9. Add remaining supported Recs formats, validating channel capacity and subtype
   through the active `soundfile` backend.
10. Run the full Recs suite, then manual multitrack, stem, and mix DAW validation.
11. After the Recs tools are in daily use, retire `~/code/fmix` separately. Do
    not delete or change it as part of this issue.

## Additional Work Beyond The Prompt

None.
