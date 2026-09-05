# In-Memory Edit Composition

## Goal

Change composed edits so that all selected source audio and every non-final
result are materialized as NumPy arrays in memory. A composition performs its
complete sequence of edits over those arrays and writes only the final session
to disk.

The initial implementation deliberately favors simplicity over support for
recordings larger than RAM. Use `np.ndarray` with `float32` samples throughout.
Do not add streaming, temporary files, memory mapping, chunk caches, or a
pluggable tensor backend yet.

Standalone edits retain their current CLI, files, and session semantics, but
use the same materialized-array renderer before writing their output.

## Composition Semantics

A composition becomes one in-memory audio calculation:

```text
source files -> NumPy arrays -> child 1 -> child 2 -> ... -> final encoder
```

Only the final child has an encoded representation. Every earlier boundary is
an unencoded `float32` array. This avoids intermediate file I/O and
generational codec loss, and normalization can inspect and scale an already
materialized result without rerendering its inputs.

An explicitly requested `format` or `subtype` on a non-final composition step
must be rejected. Ignoring it would be misleading, while honoring it would
require an encode/decode boundary. Recipe-provided paths and encoding defaults
are storage policy rather than processing semantics for non-final children;
the compiler discards them after using their output IDs and channel widths to
define the next virtual session. The final step's format, subtype, and paths
remain effective.

Options that change samples or timing remain effective at every stage. These
include clipping, stitching, splitting, mixing, gain, routing, automation,
normalization, and autocalibration.

This replaces disk-backed child execution inside compositions. Do not add a
second composition mode or silently fall back to intermediate files when
memory is insufficient.

## Materialized Audio

Add an ordinary runtime class in `recs/edit/materialized.py`:

```python
class MaterializedAudio:
    samples: np.ndarray
    sample_rate: int
    start_frame: int
    observed_ranges: list[FrameRange]
```

`samples` always has shape `(frames, channels)`, dtype `float32`, and C-contiguous
storage unless it is a deliberate NumPy view. `start_frame` maps array index
zero to the source-session timeline. `observed_ranges` contains sorted,
non-overlapping half-open source-frame ranges.

The array covers the complete extent from `start_frame` through its final
frame. Fill unobserved gaps with zero, but never infer from those zeroes that
audio was observed. Silence analysis, output segmentation, and session-record
ranges must consult `observed_ranges` and preserve gaps as gaps.

Keep this an ordinary class rather than a Pydantic data class because it owns a
large mutable runtime array and is never serialized. Persisted edit and session
descriptions remain frozen Pydantic data classes.

Provide these public operations:

- Materialize a selected track from existing session fragments.
- Select one or more channels as a view where NumPy permits it.
- Select a frame interval as a view while intersecting observed ranges.
- Concatenate explicitly stitched ranges into a new array and new timeline.
- Allocate a zeroed result for mixing or routing.
- Apply gain, automation, normalization, and limiting.
- Release an owned array when the pipeline no longer references it.

Do not hide allocations inside overloaded arithmetic. Edit operations should
make it apparent when they return a view and when they allocate storage.

## Virtual Sessions

Add frozen `MaterializedTrack` and `MaterializedSession` descriptions around
the runtime arrays. A track carries the logical identity expected by later edit
selection:

- source name and track name;
- stream ID;
- sample rate and channel count;
- timeline extent and observed ranges;
- its `MaterializedAudio` runtime object.

A materialized session contains a session ID, duration, tracks, and provenance.
It has no paths or file records because its media has not been written.

Replace command generation's assumption that every input is a
`session-record.jsonl` path with a typed session-input boundary:

- `RecordedSessionInput` describes an existing record before its selected
  tracks are loaded.
- `MaterializedSessionInput` describes an intermediate in-memory session.

Both expose the same track inventory and selector rules. Move shared
`SOURCE:TRACK[:OFFSET]` selection to this boundary so recorded and materialized
sessions reject ambiguity, mixed rates, missing tracks, and invalid offsets in
the same way.

Command generation should consume track descriptors from this interface.
During composition, bind generated source IDs directly to materialized tracks
rather than creating fake paths to nonexistent session records.

## Loading Sources

Resolve the complete composition before loading audio. Determine every source
record, selected track, channel width, and maximum timeline extent first.

Load each distinct source track at most once. If several children or selectors
use the same source channels, share the original array or NumPy views rather
than decoding duplicate copies. Decode source files directly into their final
positions in a preallocated `float32` array; do not accumulate Python lists of
blocks and concatenate them afterward.

Record the observed ranges while loading. Parallel encodings and overlapping
fragments retain the existing resolver's validation and format-selection
rules. Close every decoder immediately after its fragment has been copied.

Source arrays are read-only by default. An operation may mutate an array in
place only when pipeline liveness proves that it is the sole remaining owner
and no canonical source or sibling output refers to it. Otherwise it must
allocate a result. This prevents one child from changing another child's input
through a shared view.

## Array Renderer

Refactor `Renderer` so it renders each graph node to a complete
`MaterializedAudio` result rather than rendering file-sized blocks. It receives
materialized sources and evaluates the graph in topological order:

1. Place clips into complete track arrays.
2. Apply clip gain and automation.
3. Route tracks and buses into newly allocated destination arrays.
4. Apply bus and route gain automation.
5. Produce each output as a view when it only selects an interval, or as a new
   array when scaling or layout requires one.
6. Apply output limiting or normalization directly to the complete output.

Normalization computes `np.max(np.abs(samples))` once, then scales the same
materialized array. It does not render its source again. When an output has a
single owner, scale in place; otherwise copy before scaling.

Replace the existing bounded renderer completely after its regression tests pass.
Standalone and composed arrangement edits must use this one array renderer; do
not retain parallel block and array implementations. Standalone edits pass the
result directly to their existing session materializer, while compositions pass
it to the next stage.

## Autocalibration

Adapt autocalibration to analyze `MaterializedAudio` arrays. Window-level
calculations operate on array slices and skip windows crossing unobserved
ranges. The first sustained silence still fixes one threshold for the complete
session.

After interval detection, retain each output region as a view where practical.
A segmented logical track may therefore own a list of array views plus its
source timeline ranges rather than concatenating separated regions. A later
edit reads those views as one materialized track while preserving the omitted
gaps. Concatenate only when an edit explicitly requests stitching.

Resolved thresholds are stored in the canonical composition. No intermediate
audio or child session record is written.

## Pipeline Compilation And Execution

Split composition into three phases.

### 1. Preflight

1. Validate the input record and resolve every command file.
2. Reject explicit encoding options on every non-final step.
3. Generate each child's logical edit against the preceding session inventory.
4. Validate graphs, selectors, channel widths, frame ranges, and operations.
5. Calculate conservative array shapes and a peak-memory estimate.
6. Fail before creating the destination if an operation cannot run over
   materialized arrays.

Autocalibration output ranges are not known until analysis. Estimate their
memory using the complete selected input extent. Prefer an overestimate to a
plan that can exceed its reported maximum.

### 2. Materialization

1. Decode each required source track once into a `float32` array.
2. Execute children in declaration order.
3. Construct a `MaterializedSession` from each child's logical outputs.
4. Track ownership and remaining consumers for every array.
5. Release arrays immediately after their final consumer finishes.
6. Keep the final arrays and resolved analysis results for encoding.

Execution remains deterministic and single-threaded initially. NumPy may use
its own optimized native loops, but Recs must not add multiprocessing or
parallel stage execution in this change.

### 3. Final Output

Only after preflight and all prerequisite analysis succeed, create the
destination. Write the resolved composition to `edit.toml`, create one session
record, and encode the final arrays. Send slices of the final arrays to
SoundFile so the encoder does not require another complete output copy.

Zero-child composition remains the identity and returns the original record
without loading or writing audio. A one-child composition uses the array path
and materializes its result once.

Initially support only built-in audio arrangement commands and
autocalibration. Reject MIDI, OSC, external, stateful, nondeterministic, or
otherwise unsupported operations before loading source audio.

## Memory Accounting

Calculate and report memory in bytes using actual array shapes:

```text
bytes = frames * channels * 4
```

The preflight estimate must include:

- distinct decoded source arrays;
- simultaneously live intermediate arrays;
- mix, routing, concatenation, and scaling outputs;
- copies required because a source or view has multiple owners;
- conservative autocalibration outputs;
- small analysis arrays and metadata where material.

Views contribute no sample storage but keep their owner alive. The liveness
calculation must therefore retain a base array until every dependent view is
dead. Report both total source size and estimated peak live memory in dry-run
output.

Do not select a fixed default memory limit in this implementation. Catch
`MemoryError`, close all resources, and report the estimate and failed
allocation. The estimate allows the user to decide whether a composition is
appropriate for the machine. An operating-system allocation failure may still
terminate the process, which is an accepted limitation of this initial
array-first design.

For scale, one hour of 18-channel, 48 kHz `float32` audio occupies about
12.4 GB. Views are cheap, but several live mixed or transformed copies can
exceed a 64 GB machine.

## Canonical Composition And Provenance

The composition output is one ordinary final session:

```text
2026-09-06 11-30-00 edit/
  edit.toml
  session-record.jsonl
  audio/
    ...
```

Its `edit.toml` stores every resolved logical stage, including selectors,
timing, routing, gain, automation, normalization, output track IDs, and
autocalibration thresholds. Store paths and encoding settings only for the
final stage. Give stages and intermediate tracks stable IDs so later stages do
not refer to nonexistent child directories.

Original record and file sources retain canonical source references. The final
session's `edit_started` event points to the root `edit.toml` and adds only
execution facts not duplicated there. File events describe final media only.
There are no intermediate session records, file events, or numbered child
directories.

## Failure Handling

Fail without creating the destination when command resolution, selector
resolution, graph validation, memory estimation, or autocalibration analysis
fails. Always release references to materialized arrays and close any source
decoders.

Once final encoding begins, retain existing truthful partial-session behavior:
write final file events as work starts and finishes, append a warning on
failure where possible, and leave completed final files intact. There are no
intermediate sessions to preserve or roll back.

Do not retry with disk-backed intermediates after allocation failure.

## Dry Run

Dry run performs command resolution, graph compilation, shape calculation,
memory estimation, and autocalibration analysis. Autocalibration requires
loading its selected audio, so dry run may allocate source arrays, but it writes
no destination.

Report:

- the original input record;
- each stage, selected inputs, and logical outputs;
- frame extents, observed ranges, and channel widths;
- source-array memory and estimated peak live memory;
- allocations versus views for each stage;
- resolved autocalibration thresholds;
- final format, subtype, paths, and duration;
- confirmation that no intermediate media will be written.

Release all dry-run arrays before returning.

## NumPy First, Other Storage Later

Use direct NumPy operations in the initial implementation. Keep edit operations
as explicit functions taking and returning `MaterializedAudio`; do not create a
generic tensor API solely for a possible future Torch port.

A later Torch implementation can replace the array operations after profiling.
`torch.compile` may fuse substantial DSP graphs, but simple gain, slicing, and
copying are often limited by memory bandwidth, so speedups must be measured
rather than assumed.

Likewise, a later memory-mapped implementation can change selected owned arrays
to `np.memmap`. The initial ownership, shape, liveness, and observed-range
metadata should remain applicable, but memory mapping is not part of this
change.

## Implementation Order

1. Add `MaterializedAudio`, exact source loading, views, observed-range
   handling, and ownership tests.
2. Add session-input track inventory and selector resolution for recorded and
   materialized sessions.
3. Add conservative shape, liveness, and peak-memory planning.
4. Replace the renderer with complete-array execution for standalone and
   composed arrangement edits, including mixing, automation, limiting, and
   normalization.
5. Compile ordinary composition children into materialized sessions and remove
   disk-backed child execution.
6. Adapt autocalibration to analyze arrays and expose retained regions as
   materialized views.
7. Materialize only the final session and replace composition provenance and
   canonical TOML accordingly.
8. Add dry-run allocation and memory reporting, plus resource cleanup on every
   exit path.
9. Run the complete verification sequence and compare final samples with
   equivalent standalone lossless edit chains at exact frame boundaries.

Keep each implementation commit independently passing. Once the array renderer
handles all existing operations, remove the old block renderer in the same
commit so there is only one execution path.

## Tests

Use 48 kHz WAV fixtures at least one second long for audio tests.

1. Materialize segmented mono, stereo, and multichannel tracks into exact
   `float32` arrays.
2. Preserve source gaps as unobserved ranges even though their array cells are
   zero.
3. Verify channel and frame selections use views and retain correct base-array
   ownership.
4. Verify mutations are forbidden while arrays or views have multiple owners.
5. Verify source files are decoded once when reused by several selectors or
   stages.
6. Render clip, stitch, split, mix, routing, gain, and automation as complete
   arrays with exact sample results.
7. Normalize and limit without rerendering upstream arrays.
8. Verify array liveness releases each allocation after its final consumer and
   that peak measured storage does not exceed the estimate.
9. Compose several ordinary edits without creating intermediate directories or
   files.
10. Run autocalibration over an upstream array and feed its retained views into
    a later edit.
11. Preserve gaps and timeline positions through every stage and in final file
    records.
12. Verify multiple tracks and outputs retain stable selector identities.
13. Reject explicit non-final `format` or `subtype` before loading audio or
    creating the destination.
14. Reject unsupported media and operations before loading audio.
15. Verify canonical `edit.toml` contains resolved stages and thresholds but no
    intermediate paths or encoding claims.
16. Verify the final session record contains only final media and points to the
    canonical composition.
17. Verify dry run reports memory and writes nothing, including when it must
    load arrays for autocalibration.
18. Inject preflight, allocation, analysis, and final-write failures and verify
    resource cleanup and truthful destination state.
19. Verify zero-child identity and one-child composition behavior.
20. Compare the final encoded samples against equivalent standalone lossless
    edit chains within the final subtype's precision.

## Acceptance Criteria

- A non-empty composition writes exactly one final session and no intermediate
  media or session records.
- Selected source tracks are decoded once and held as `float32` NumPy arrays.
- Every intermediate result is an array or array view, never a file-backed
  temporary or replayable stream.
- Normalization scans and scales its materialized input without recomputing
  upstream edits.
- Views, ownership, and liveness avoid unnecessary copies and release dead
  arrays promptly.
- Dry run reports a conservative peak-memory estimate.
- Explicit non-final encoding requests fail instead of being ignored.
- Source gaps, timeline positions, channel layouts, and selector identities
  remain correct.
- Canonical composition TOML fully describes logical stages and final encoding
  without references to nonexistent child files.
- Standalone edit output and session behavior remain unchanged, while its
  rendering also uses materialized arrays.

## Additional work beyond the prompt

None.
