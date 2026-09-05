# In-Memory Edit Composition

## Goal

Change composed edits so that non-final child sessions are never written to
disk. Keep each intermediate result as a typed, replayable virtual session and
pass bounded NumPy audio blocks through the chain. Materialize only the final
child as an ordinary edit session containing `edit.toml`,
`session-record.jsonl`, and media files.

This must not load complete recordings into memory. "In memory" refers to the
intermediate session descriptions, media graph, analysis state, and bounded
audio blocks. Original source media remains on disk and may be decoded again
when a later analysis requires another pass.

Standalone edits retain their current behavior and always produce an ordinary
session directory.

## Semantic Change

Composition becomes a pipeline of logical media transformations rather than a
sequence of encode/decode operations:

```text
source files -> child 1 graph -> child 2 graph -> ... -> final encoder
```

Every non-final audio boundary uses Recs' internal `float32` sample
representation. No intermediate codec, bit depth, file name, or container is
observable. This avoids generational loss and makes the result independent of
temporary storage.

An explicitly requested `format` or `subtype` on a non-final composition step
must be rejected. Silently ignoring it would be misleading, while reproducing
the effect of arbitrary lossy codecs would require materializing their encoded
streams. The final step continues to accept `format` and `subtype` and controls
the files written to the result session.

Recipe-provided output paths and encoding defaults are storage policy, not DSP
semantics, for non-final children. The pipeline compiler discards them after it
has used the output IDs and channel widths to define the virtual tracks. User
options that affect samples or timing, including gain, normalization, routing,
automation, clipping, stitching, splitting, and autocalibration, remain
effective at every stage.

This replaces disk-backed child execution inside a composition. Do not add a
second composition mode or a temporary-file fallback. Reject an operation that
cannot satisfy the virtual-session contract.

## Virtual Media Model

Introduce a small synchronous, pull-based media interface in
`recs/edit/media.py`:

```python
class AudioStream(Protocol):
    sample_rate: int
    channels: int
    ranges: list[FrameRange]

    def read(self, start: int, end: int) -> np.ndarray: ...
    def close(self) -> None: ...
```

`read()` returns a two-dimensional `float32` array and may be called repeatedly
or out of order. It must be deterministic and replayable because normalization
and autocalibration make multiple passes. Reads cannot cross an unobserved
range; timeline gaps remain explicit rather than becoming synthetic silence.

Provide concrete stream implementations only for current needs:

- `FileAudioStream` reads existing session fragments or a direct audio file.
- `RenderedAudioStream` exposes one arrangement output without encoding it.
- `SlicedAudioStream` exposes the retained ranges produced by autocalibration
  while preserving their original timeline positions.

Do not make these Pydantic data classes. They own decoder handles and runtime
state. Keep persisted descriptions in frozen Pydantic models and runtime stream
objects in ordinary classes.

Add frozen `VirtualTrack` and `VirtualSession` data classes. A virtual track
contains the same logical identity required by edit source selection:

- source name and track name;
- stream ID;
- sample rate and channel count;
- observed half-open frame ranges;
- its runtime `AudioStream`.

A virtual session contains a session ID, duration, tracks, and provenance. It
does not pretend to have paths or `file_started`/`file_finished` records because
no files exist.

## Session Input Abstraction

Replace command generation's assumption that every input is a
`session-record.jsonl` path with a typed `SessionInput` abstraction. It provides
track inventory, selector resolution, timing metadata, and audio streams.

Implement two sources of that interface:

- `RecordedSessionInput` adapts an existing session record and its files.
- `VirtualSessionInput` adapts an intermediate `VirtualSession`.

Move the shared selector rules currently embedded in session-record parsing to
this boundary. Both implementations must accept `SOURCE:TRACK[:OFFSET]`, reject
ambiguity consistently, preserve source gaps, and enforce one sample rate for
the selected audio.

Command generation should consume track descriptors from `SessionInput`
instead of reopening a record path. `SourceSpec.record` remains the persisted
syntax for standalone arrangements. During composition compilation, bind each
generated source ID directly to a virtual or recorded stream rather than
inventing a path to a nonexistent record.

Do not write temporary session records merely to satisfy existing APIs.

## Block Renderer

Refactor `Renderer` so its primary operation renders a requested node and frame
range to a NumPy block:

```python
def render(self, node: str, start: int, end: int) -> np.ndarray: ...
```

The renderer receives resolved `AudioStream` objects rather than opening
`ResolvedSource.fragments` itself. Preserve the existing graph, automation,
channel-width, gap, and clipping semantics.

`RenderedAudioStream` wraps a renderer plus one output node and applies that
output's gain and normalization. The current file-writing method becomes a
thin materializer that repeatedly calls `render()` and sends blocks to the
final encoder.

Normalization remains replayable and bounded: one pass computes the peak and a
later pass emits scaled blocks. Cache the computed scale on the virtual output,
but do not cache the complete waveform. Multiple downstream reads may rerender
upstream stages; this is the intentional CPU-for-disk tradeoff.

Keep one bounded LRU of open source decoders per pipeline execution. Closing a
virtual session closes its complete upstream graph exactly once.

## Autocalibration

Adapt autocalibration to consume `AudioStream` rather than
`ResolvedSource.fragments`. Its existing histogram passes already use bounded
memory and can read a replayable stream repeatedly.

After calibration and silence detection, expose each selected track as a
`SlicedAudioStream` containing its retained source-frame ranges. Do not encode
those ranges or create a child session record. Persist the resolved thresholds
inside the canonical composition so the completed pipeline can be reproduced
without deriving different calibration later.

Autocalibration followed by another analysis may render upstream audio several
times. Do not spill to disk automatically. Report the expected pass count in
dry-run output so expensive compositions are visible before execution.

## Pipeline Compilation

Split composition into compilation and materialization:

1. Validate the input record and resolve every command file.
2. Reject explicit encoding options on every non-final step.
3. Generate each child's complete logical edit against the current
   `SessionInput`.
4. Validate its graph and bind its sources to current audio streams.
5. Convert its outputs into a new `VirtualSessionInput` for the next child.
6. Run required analyses, including normalization peaks and autocalibration,
   while keeping their resolved results in memory.
7. Only after all stages compile and all prerequisite analyses succeed, create
   the destination and materialize the final virtual session.

Compilation returns a frozen `PreparedComposition` containing the resolved
composition, original recorded inputs, virtual stages, final tracks, and an
estimated source-decode pass count. Execution must not resolve commands or
selectors again.

Zero-child composition remains the identity and returns the original record
without writing anything. A one-child composition uses the same pipeline path
and materializes that child's result once.

Initially support only the built-in audio arrangement commands and
autocalibration. Reject future MIDI, OSC, external, stateful, nondeterministic,
or non-replayable operations until they implement the same virtual-session
contract.

## Canonical Composition And Provenance

The composition output is one ordinary final session, not a container of child
sessions:

```text
2026-09-06 11-30-00 edit/
  edit.toml
  session-record.jsonl
  audio/
    ...
```

Its `edit.toml` is the resolved composition. Store each stage's effective
logical edit, including selectors, timing, routing, gain, normalization, output
track IDs, and resolved autocalibration thresholds. Store final encoding and
paths only for the final stage. Non-final stages must contain no fictitious
media paths or formats.

Give every stage and virtual track a stable ID within the composition. Later
stages refer to those IDs, not to `../001-child/session-record.jsonl`. Original
record and file sources retain their ordinary canonical source references.

The final session's `edit_started` event points to the root `edit.toml` and adds
only execution facts not duplicated there. `file_started` and `file_finished`
events describe final media only. There are no intermediate session records,
file events, or child directories.

## Failure Handling

Fail without creating the destination when command resolution, selector
resolution, graph validation, or prerequisite analysis fails. This includes an
unsupported virtual operation or a non-final explicit encoding request.

Once final encoding begins, preserve the existing truthful partial-session
behavior: write final file events as work starts and finishes, append a warning
on failure where possible, and leave completed output intact. There are no
completed intermediate sessions to preserve.

Always close source decoders after success, failure, or interruption. Do not
retain whole audio blocks beyond the current bounded render request.

## Dry Run

Dry run performs command resolution, pipeline compilation, and analyses but
writes no destination. Report:

- the original input record;
- each stage, its selected virtual inputs, and logical outputs;
- frame ranges and channel widths;
- analysis passes required by normalization or autocalibration;
- the estimated number of source decode passes;
- the final format, subtype, paths, and duration;
- confirmation that no intermediate media will be written.

The estimate need not predict wall-clock time. It must make repeated upstream
rendering apparent.

## Implementation Order

1. Add `AudioStream`, `FileAudioStream`, virtual track/session data classes,
   and exact block-read tests over segmented sources and gaps.
2. Refactor `Renderer` to consume streams and expose bounded block rendering;
   keep standalone edit output byte-equivalent through the existing
   materializer.
3. Add `SessionInput` and convert selector resolution and command generation to
   accept recorded or virtual sessions without fake record paths.
4. Compile ordinary composition children into virtual sessions and materialize
   only the final child. Remove numbered child-directory execution.
5. Adapt normalization and autocalibration to replay virtual streams and record
   resolved analysis in canonical composition TOML.
6. Replace the canonical composition layout and session provenance with one
   final session and stable stage IDs.
7. Expand dry-run reporting, rejection messages, and resource cleanup.
8. Remove disk-backed composition-only code after all callers use the virtual
   pipeline.
9. Run the complete verification sequence and compare representative
   compositions against equivalent standalone lossless edit chains at exact
   sample boundaries.

Each implementation commit must keep standalone edits and already-supported
composition operations passing. Do not leave parallel renderers or source
resolvers after the migration is complete.

## Tests

Use 48 kHz WAV fixtures at least one second long for audio tests.

1. Verify block reads through file, rendered, and sliced streams, including
   channel selection, segment boundaries, and source gaps.
2. Verify standalone edit output is unchanged after the renderer refactor.
3. Compose clip, stitch, split, mix, gain, routing, and automation without
   creating intermediate directories or files.
4. Verify a many-stage composition keeps memory bounded by instrumenting block
   sizes and retained arrays.
5. Verify normalization makes its analysis pass and produces the same samples
   as an equivalent lossless standalone chain within the final subtype's
   precision.
6. Verify autocalibration can consume a virtual upstream track, replay it for
   analysis, and feed its sliced output into a later ordinary edit.
7. Verify gaps remain gaps through every virtual stage and split final file
   records correctly where required.
8. Verify multiple tracks and multiple outputs retain stable selector identity
   between stages.
9. Reject explicit `format` or `subtype` on a non-final step before creating the
   destination.
10. Reject unsupported, stateful, or non-replayable operations before output.
11. Verify canonical `edit.toml` contains all resolved stages and thresholds but
    no intermediate paths or encoding claims.
12. Verify the final session record contains only final media and points to the
    canonical composition.
13. Verify dry-run writes nothing and reports stages, passes, final encoding,
    and the absence of intermediate media.
14. Inject failures during preflight, analysis, first final write, and later
    final writes; verify destination creation and partial records are truthful.
15. Verify all stream and decoder resources close on success, errors, and
    keyboard interruption.
16. Verify zero-child identity and one-child composition behavior remain
    correct.

## Acceptance Criteria

- A non-empty composition writes exactly one final session and no intermediate
  media or session records.
- Memory use is bounded by render blocks, histograms, graph metadata, and track
  ranges rather than recording duration.
- Every intermediate audio sample remains `float32` until final encoding.
- Current deterministic audio edits and autocalibration can consume virtual
  outputs and be replayed for multi-pass analysis.
- Explicit non-final encoding requests fail instead of being ignored.
- Original source gaps, timeline positions, channel layouts, and selector
  identities remain correct.
- Canonical composition TOML fully describes the virtual stages and final
  encoding without references to nonexistent child files.
- Standalone edit behavior remains unchanged.

## Additional work beyond the prompt

None.
