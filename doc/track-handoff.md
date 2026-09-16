# Aligned track handoff

`recs session handoff RECORDING --clock CLOCK --start-frame START --end-frame END`
prints a JSON plan without rendering. Add `--destination NEW_DIRECTORY` to render
the bundle. `--tracks ID ...` selects exact recording stream IDs; omitting it
selects all audio streams on that clock. IDs are sorted for deterministic filenames.

The first profile is 32-bit float WAV plus `handoff.json`. Each file has the same
sample rate and `END - START` frames, preserving the recorded channel order.
Import every file at the same editor position. File frame zero corresponds to
source-clock frame `START`. There is no level normalization or integer quantization.

Only sealed, unlinked recording segments are supported in this version. The
interval must be nonempty, nonnegative, and within every selected track's extent.
All tracks must share one integer-rate capture clock. Unmapped fragments, mixed
clocks, and incompatible media metadata are rejected before generating output.
There is no resampling, inferred synchronization, or drift correction.

Known gaps render as silence. The sidecar preserves their reasons, so intentional
silence suppression is distinguishable from missing capture. It does not assert
that silent samples were captured during a gap.

## Sidecar version 1

`handoff.json` contains:

- `version`: `1`.
- `recording`: original absolute recording-document path, for provenance only.
- `clock`, `sample_rate`: the original clock identity and integer rate in Hz.
- `start_frame`, `end_frame`: original half-open source interval. Subtract
  `start_frame` from any position below to obtain the corresponding WAV position.
- `encoding`: `WAV/FLOAT`.
- `tracks`: ordered entries containing `stream_id`, `source_id`, optional
  `source_name` and `track_name`, channel labels in file order, relative WAV `path`,
  and `gaps`. Each gap retains its source-frame `start`, `end`, and original
  `reason`, clipped to the exported interval.
- `markers`: numbered original markers with labels, timestamps, and source-frame
  evidence on the selected clock. Only markers in `[START, END)` are included;
  unpositioned markers are not assigned invented positions. Frame positions remain
  in original source coordinates, not relative WAV coordinates.

Files are named `audio/0001.wav`, `audio/0002.wav`, and so on. Names and identities
remain in the sidecar, avoiding filename interpretation or sanitization collisions.
The bundle also includes the ordinary `edit.toml`, `recording.toml`, and capture
journal produced by the shared editor. The journal contains the same handoff data
as edit provenance; the WAVs and sidecar can be used independently of recs.

Originals are never modified. The destination must be new and outside the source
session. Rendering and sidecar writing finish in a sibling staging directory
before publication. Failures retain any partial work at the reported staging path
without presenting the requested destination as a completed bundle.
