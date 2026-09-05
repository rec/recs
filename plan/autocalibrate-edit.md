# Autocalibrating Silence Edit

## Purpose

Add a non-destructive edit that recovers useful recordings from a session made
without suitable per-track noise calibration. The edit measures the actual noise
level independently for each selected audio track, derives a new silence
threshold, reruns silence detection, and writes the retained regions as a new
Recs session.

The source session is never modified. This is particularly useful after
`record_everything` captured continuous audio, or when a noisy input caused the
original recorder to leave a file open for most of a session.

```text
recs edit autocalibrate [RECORD]
recs edit autocalibrate [RECORD] --channel SOURCE:TRACK
```

With no channel selectors, process every complete audio track in the source
record. Calibration is deduced entirely from the recorded samples. No live
measurement, saved hardware calibration, or user-designated quiet interval is
required or accepted.

Use the existing `clip` edit before or after this edit when only a timeline
subset should appear in the result. Do not add a second set of output-cropping
options to `autocalibrate`.

## Why This Is A Separate Edit Kind

The current `EditSpec` is a declarative arrangement with a known set of outputs.
Autocalibration is analysis-dependent: it discovers one threshold per track and
then produces zero or more files per track according to the detected activity.
Those files must retain one stable logical track identity even though their
number is not known before analysis.

Do not force this operation into the arrangement graph by generating one output
and one track name for every detected region. Add a separate versioned
`AutocalibrateEdit` Pydantic data class, analogous to `CompositionEdit`, and a
dedicated executor. It remains a normal session-to-session edit and uses the
same command discovery, selector resolution, output validation, session-record
writer, and CLI destination rules where their contracts fit.

The packaged command is `recs/edit/commands/autocalibrate.toml`. A TOML recipe
can supply defaults, but it cannot replace the built-in analysis or execute
user-provided Python.

## Terminology And Units

Recs currently expresses `noise_floor` as positive decibels below full scale.
For example, `noise_floor = 70` means a threshold of `-70 dBFS`. A physically
higher threshold therefore has a numerically smaller `noise_floor` value.

Use that existing representation in canonical TOML and at the shared silence
decision boundary. In user-facing reports, print both forms to avoid ambiguity:

```text
X18:1-2 measured noise: -48.2 dBFS
X18:1-2 silence threshold: -42.2 dBFS (noise_floor = 42.2)
```

The threshold must be above the measured noise by `signal_margin_db`. In the
existing positive-attenuation convention:

```text
noise_floor = measured_noise_floor - signal_margin_db
```

Do not reuse the live calibration expression that adds `preview_headroom` to
the positive attenuation value. That intentionally favors sensitivity and does
not suppress the measured noise, so it is unsuitable for this recovery edit.

## Requested And Resolved TOML

The requested edit may omit derived thresholds:

```toml
schema_version = 1
kind = "autocalibrate"
record = "../source/session-record.jsonl"
channels = ["X18:1-2", "X18:3-4"]

[calibration]
window_frames = 4800
candidate_percentile = 20.0
candidate_tolerance_db = 3.0
minimum_silence_frames = 24000
noise_percentile = 95.0
signal_margin_db = 6.0
analysis_floor_dbfs = -160.0

[silence]
quiet_before_frames = 48000
quiet_after_frames = 96000
stop_after_quiet_frames = 960000
shortest_file_frames = 48000
longest_file_frames = 0

[output]
format = "flac"
subtype = "pcm_24"
```

Human CLI durations are accepted through Reccy units and converted to integer
frames before canonical TOML is written. All selected tracks must share the
declared sample rate, matching the current audio editor restriction.

After analysis, write a fully resolved `edit.toml` containing one result for
each selected logical track:

```toml
[[thresholds]]
source = "X18:1-2"
silence_start = 1440000
silence_end = 3297600
measured_noise_floor = 48.2
noise_floor = 42.2
window_count = 387
```

`source` is the stable selector join key. `silence_start`, `silence_end`,
`measured_noise_floor`, and `window_count` describe the first sustained silence
used for calibration; `noise_floor` is the value used by silence detection. A
resolved file can be executed again without recalibrating. The detector algorithm
and schema version define how activity intervals are recomputed from the source
samples.

Write `edit.toml` after successful analysis and before creating any output audio.
An analysis failure therefore leaves no partial destination. Once output begins,
the ordinary session record describes partial success or interruption.

## Calibration Analysis

Analyze every selected logical track independently. A configured stereo or
multichannel track receives one threshold because that matches current recording
behavior. Selecting `SOURCE:TRACK:OFFSET` explicitly calibrates and emits one
channel instead. Once the first sustained silence is found for a track, its
calibration is fixed for the complete edit. Do not adapt the threshold later in
the session.

Read source fragments through the existing session-record resolver. Do not
calibrate from zero-filled record gaps: no samples were observed there. Resolve
parallel encodings with the same format preference and ambiguity rules as other
audio edits.

Partition all available source samples into fixed, non-overlapping windows
aligned to the source session timeline, not to individual file starts or decoder
block sizes. For every completely observed window, calculate the same level used
by current silence detection:

1. Find `(maximum - minimum) / 2` for each channel.
2. Average those amplitudes across the logical track.
3. Convert the result to dBFS.
4. Clamp exact digital silence to `analysis_floor_dbfs` so canonical TOML never
   contains infinity.

Discover the first silence in two bounded analysis passes:

1. Build a fixed-resolution histogram of all finite window levels and find the
   configured `candidate_percentile`, initially 20. This supplies a provisional
   quiet level without retaining one value per window.
2. Rescan windows in source-time order and find the first contiguous observed
   run lasting at least `minimum_silence_frames` whose levels do not exceed the
   provisional level plus `candidate_tolerance_db`.
3. Build a histogram only for that first run and use its configured upper
   `noise_percentile`, initially 95, as the measured noise floor.
4. Add `signal_margin_db` in dBFS, or equivalently subtract it from Recs' positive
   attenuation value, to obtain the fixed silence threshold.

Histogram bin width is part of the versioned algorithm and initially 0.1 dB.
This keeps memory constant for recordings of any length. Exact digital silence
participates at `analysis_floor_dbfs`; source-record gaps do not participate at
all because no samples were captured there.

The initial percentile is only a way to locate the quiet population. The actual
calibration comes from the first sustained silence matching that population, not
from a live environment or a user-selected range. This assumes the track contains
at least one sustained silence and that its noise characteristics do not change
after that first silence. Print this assumption in command help and dry-run
output.

This is a retrospective edit, so the provisional quiet population may use samples
from the complete recording. Once that population has identified the earliest
matching sustained silence, only that first silence determines the fixed
calibration. Later quiet regions never revise it.

Reject a selected track when there are no complete observed windows or no
sustained silence can be discovered. Report the selector, provisional quiet
level, required duration, and closest candidate duration. Do not silently borrow
another track's threshold or fall back to live or global recording configuration.

## Silence Detection And Segmentation

After resolving thresholds, scan the selected tracks in bounded blocks. Detection
windows use the same source-timeline alignment and level calculation as
calibration. A window is active when its amplitude is greater than or equal to
`db_to_amplitude(noise_floor)`.

Convert active windows into half-open source-frame intervals:

1. Extend the first active frame backward by `quiet_before_frames`, bounded by
   observed source coverage.
2. Extend the last active frame forward by `quiet_after_frames`, likewise bounded.
3. If two active regions are separated by no more than
   `stop_after_quiet_frames`, retain the complete intervening audio and emit one
   continuous file.
4. Otherwise emit separate files and omit the middle quiet region.
5. Merge overlapping padded intervals.
6. Drop retained intervals shorter than `shortest_file_frames`.
7. Split retained intervals at `longest_file_frames` when nonzero, without
   changing their source-timeline positions.

Never concatenate separated source intervals into one file while claiming that
the file covers the omitted source frames. Every emitted file must contain a
continuous source-frame interval, and its `quantity_count` must equal the number
of encoded frames.

A gap in the source record always breaks an output interval. It cannot be filled
or classified as observed silence by this edit. Activity before and after a gap
becomes separate files even when the gap is shorter than
`stop_after_quiet_frames`.

Do not honor `record_everything` during this edit. Its purpose is specifically to
rerun silence detection on audio that may have been captured with
`record_everything` enabled.

## Output Session

Create one ordinary output session directory:

```text
2026-09-06 11-30-00 edit/
  edit.toml
  session-record.jsonl
  audio/
    x18-1-2/
      0001.flac
      0002.flac
    x18-3-4/
      0001.flac
```

Use a stable legal directory name derived from each selector and a one-based,
zero-padded file index. All files for one selected track use:

- `source = "edit"`;
- one stable `track_name` derived from the selector;
- the selected source channel order and width;
- the source sample rate;
- one stable stream ID across that track's files;
- `frame_count` values in the original source-session timeline.

Write matching `file_started` and `file_finished` entries. The start frame is the
retained interval's first frame, the finished frame is its exclusive end, and
`quantity_count = end - start`. This makes the result directly consumable by
later Recs edits as a segmented logical track.

If a selected track has no active interval, write no media file for it. The edit
still succeeds, and the resolved threshold remains in `edit.toml`. Do not create
empty placeholder audio.

Only selected audio is emitted. MIDI, OSC, unselected tracks, recording events,
and other media are omitted under the existing edit session-transformation rule.

The source record and every source audio file remain untouched. Even when one
input file is retained in full, write a new output file rather than making the
new session depend on media outside its own directory.

## Session Record Events

The output uses the standard `recs edit` session header and footer. Its
`edit_started` event points to `edit.toml` and contains only resolved facts that
are not already in that file. The calibration settings, measurements,
thresholds, selectors, and source record are canonical edit data and must not be
duplicated in the event.

Warnings belong in the session record only for conditions observed after
`edit.toml` is written, such as a decoder or output failure. Calibration errors
before output creation are ordinary command errors.

## CLI And Dry Run

Extend the edit dispatcher to recognize `kind = "autocalibrate"` and add the
packaged command:

```text
recs edit autocalibrate [RECORD] [OPTIONS]
```

Support these operation-specific options through one frozen Pydantic Tyro data
class rather than adding them to `EditOptions`, because composition, clipping,
mixing, and autocalibration do not share them:

- repeated `--channel SOURCE:TRACK[:OFFSET]`;
- `--window-time`;
- `--candidate-percentile`;
- `--candidate-tolerance-db`;
- `--minimum-silence-time`;
- `--noise-percentile`;
- `--signal-margin-db`;
- the five existing silence timing values;
- output `--format` and `--subtype`;
- `--destination` and `--dry-run`.

`--dry-run` performs source resolution and sample-derived calibration analysis,
but writes no files or directories. Print, per track, the provisional quiet
level, first discovered silence range, observed window count, measured noise,
chosen threshold, number and total duration of retained intervals, and estimated
output duration. This is the review path when the automatic estimate may have
confused quiet material with noise.

An autocalibration edit may be a child of a composition. It consumes the previous
child's session record and emits one new session like any other non-empty child.
Composition preflight must recognize the operation without trying to convert it
to a complete arrangement `EditSpec`.

## Implementation Structure

Add `recs/edit/autocalibrate.py` for the typed edit, calibration analysis,
interval detection, execution, and summary. Keep public data classes and entry
points before private bounded-analysis helpers.

Extract only genuinely shared pure operations:

- source selector and fragment resolution from `recs/edit/record.py`;
- the current block-level amplitude calculation;
- session output path validation and file-record construction where their
  contracts are identical.

Do not instantiate `ChannelWriter` for offline editing. It owns live recording
threads, wall-clock timestamps, buffering, mutable configuration, and file-open
state that do not belong in a deterministic file edit. The offline interval
builder should implement the documented silence policy directly over source
frames.

Keep memory bounded by the configured read block, one analysis window per track,
the fixed histograms, and the list of retained intervals. Do not load complete
recordings or per-window level histories into NumPy arrays. CPU and I/O cost are
one decode pass to build the global level histogram, one decode pass to find and
measure the first sustained silence, one decode pass for final detection, and one
decode/encode pass over retained intervals. Keep these passes explicit and
deterministic initially; optimize only after profiling real sessions.

Do not add parallel track processing initially. Sequential bounded reads avoid
competing FLAC decoders, excess memory, and unpredictable disk seeking. A later
performance change should be based on measured recordings.

## Errors And Edge Cases

Fail before creating the destination for:

- an unreadable or structurally invalid source record;
- no selected finished audio;
- unknown or ambiguous selectors;
- mixed selected sample rates;
- no complete observed analysis window for a selected track;
- no sustained silence matching the provisional quiet population;
- an unsupported output format, subtype, or channel width;
- an existing destination;
- invalid percentiles, tolerance, margin, window, or silence timing values.

Treat parallel source encodings, overlapping fragments, missing files, and
source gaps according to the existing editor's rules. A truncated final source
file is usable only to the extent already accepted by the session-record reader
and audio decoder; do not invent recovery behavior in this feature.

## Tests

Use 48 kHz WAV fixtures of at least one second for every audio test. Cover:

1. Independent thresholds for a low-noise and high-noise track containing the
   same foreground bursts.
2. Discovery of the first sustained silence after opening program material and
   discovery when the session begins with silence.
3. Mono offsets from a configured stereo track and one threshold for an
   unseparated stereo track.
4. Fixed source-timeline window alignment across multiple source files.
5. Source gaps excluded from silence discovery and forced to split output files.
6. Threshold crossings, quiet padding, merging, minimum duration, and maximum
   file duration at exact frame boundaries.
7. A noisy track becoming several correctly indexed files while a selected
   digital-silence track emits none.
8. Stable stream ID and track name across multiple files, with exact start,
   finish, and quantity frame counts in the output session record.
9. Canonical TOML containing the first discovered silence and resolved thresholds,
   then executing again without any calibration analysis pass.
10. Dry-run measurements and interval summaries without filesystem output.
11. Bounded reader behavior on an instrumented long source.
12. Rejection cases listed above before destination creation.
13. Composition with autocalibration followed by an ordinary `clip`, `split`, or
    `mix` edit.
14. Source record and source audio byte-for-byte unchanged after success and
    failure.
15. A later noise-level change that does not alter the threshold established from
    the first discovered silence.

Run the full Recs verification sequence after each implementation commit. Manual
validation should use the uncalibrated session that motivated this feature and
compare detected regions and false triggers per track before relying on the
result.

## Implementation Order

1. Add the requested and resolved `AutocalibrateEdit` data classes, canonical
   TOML, validation, command recipe, dispatcher recognition, and CLI parsing.
2. Add bounded per-track first-silence discovery, fixed calibration, and dry-run
   threshold reporting.
3. Add deterministic silence interval detection with exact frame-boundary tests.
4. Add segmented output encoding and unified session-record entries.
5. Make autocalibration a valid composition child without changing complete
   arrangement behavior.
6. Run all automated checks, then validate against the original noisy session.

## Non-Goals

- Do not modify or persist live recording configuration.
- Do not recalibrate attached hardware.
- Do not perform spectral denoising, hum removal, gating, compression, or gain
  normalization.
- Do not infer songs, takes, or semantic event boundaries.
- Do not alter MIDI, OSC, or other media.
- Do not replace current edit source paths with volume UUID references as part
  of this feature.

## Additional work beyond the prompt

None.
