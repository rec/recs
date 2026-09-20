# recs: the Universal Recorder

See [plans and ownership](plan/README.md) for implemented contracts, remaining
proposals, and the boundaries between recs, uFor, and enge.

recs continuously records audio, MIDI, OSC, and key events into timestamped
sessions. Audio can be recorded continuously or split around quiet passages.
Each completed session has a `recording.toml` indexing its media and native
timelines. Its `session-record.jsonl` preserves capture lifecycle, source,
configuration, disk, and control events.

The recorder is designed to run unattended. It discovers selected audio and
MIDI devices after startup, resumes when devices return, monitors free space,
and can continue a session on another removable disk.

## Tests

`uv run pytest` uses four workers and keeps each test file in one worker. Run
`uv run pytest -n 0` to reproduce a failure serially.

## Requirements And Installation

recs requires Python 3.13 or newer and the system libraries required by
PortAudio and libsndfile.

```console
uv tool install recs
```

Use `pip install recs` if you manage Python environments with pip.

List available audio devices without starting a recording:

```console
recs --info
```

## Recording

Run recs with no arguments to record available audio inputs in the current
directory:

```console
recs
```

By default, recs records audio as FLAC, records MIDI inputs, and omits quiet
audio between files. A run creates a timestamped session directory:

```text
2026-09-07 20-15-15/
  recording.toml
  session-record.jsonl
  audio/
    1-2 + 20260907-201515.flac
  midi/
    Launchkey-20260907-201515.jsonl
  osc/
    X18.jsonl
```

Select inputs and an output root with ordinary recording options:

```console
recs --include xr18 --output-directory /mnt/openloop/recs
```

The output directory is the root for sessions. recs computes each session
directory below it; that computed path is not configuration and is not saved.
An output-directory pattern may include time and source placeholders.

Use `--record-everything` to keep audio files open through quiet passages.
MIDI silence costs no storage and does not segment MIDI files. Configure OSC
nodes with `--osc-nodes /path/to/nodes.toml`.

Configuration values accept explicit units, for example
`--quiet-before-start 250ms`, `--longest-file-time '2 h'`, and
`--minimum-free-space 1GiB`. See
[Configuration Units](doc/configuration-units.md).

## Recording Setups

Inspect a setup without starting capture or requiring a daemon:

```console
recs readiness --profile x18-show
recs readiness --json-output -- --include xr18 --output-directory /mnt/recordings
```

Missing devices produce warnings; invalid settings, channels, and unusable output
paths produce failures (exit status 1). Inspection uses the same settings overlay
and explicit-option precedence as capture. `--save-settings` enables reading the
saved overlay when it would otherwise be disabled; readiness never writes it.
The report includes tracks, effective settings, free space, and an input-PCM
duration estimate. This is not a compression forecast or a reserved storage
guarantee. MIDI/OSC endpoint availability is not probed. Output permission checks
are read-only and do not prove a future write will succeed. Input streams are
never opened; use the separate `recs test-input` only to make an actual test
recording. `recs preflight` remains the check for an already-running daemon.

A named setup stores a complete recording configuration together with track
names and mono/stereo layouts. Options for `save` and `use` follow `--`:

```console
recs profile save x18-show -- --include xr18 --formats flac
recs profile use x18-show -- --output-directory /mnt/openloop/recs
recs profile list
recs profile show x18-show
recs profile delete x18-show
```

Start with a saved setup using `recs --profile x18-show`. Install the daemon
with the same setup using `recs daemon install --profile x18-show`.

When a setup is started with saving enabled, mutable changes made through the
protocol are stored in `~/.config/recs/profile-settings/NAME.json`. This overlay
does not alter the setup definition or the daemon's unprofiled
`~/.config/recs/settings.json` file.

Per-device JSON profiles are separate from named recording setups. Pass them
with `--profiles` to override settings such as the noise floor for a matching
device:

```json
{
  "MacBook Pro Microphone": {
    "noise_floor": 60
  },
  "FLOW 8 (Recording)": {
    "recording": {
      "noise_floor": 75
    }
  }
}
```

## Daemon And Control

recs can install and manage a per-user background service:

```console
recs daemon install --output-directory /mnt/openloop/recs
recs daemon status
recs daemon restart
recs daemon stop
recs daemon uninstall
```

Inspect and control the newest foreground recorder, or the daemon when no
foreground recorder is running:

```console
recs watch
recs control status
recs control disk
recs control mark "solo starts"
recs control pause
recs control resume
recs control card-replace
recs control instances
recs control --daemon status
recs control --instance -1 pause
```

The complete local RPC and event interface, including live waveforms and the
`new_session` command, is documented in [recs Protocol](doc/recs_protocol.md).

## Sessions And Editing

The bare `recs` command starts capture. `recs sessions ROOT` lists recordings;
`recs session COMMAND` operates on one session. `recs record check PATH` validates
a recording document and its media; it does not start recording. The old implicit
`recs session PATH` listing shorthand is not supported.

For a running instance, `control pause` and `control resume` affect capture.
`control stop`, `control pause-playback`, and `control continue` affect playback.
Resuming capture stops playback first; stopping playback restores capture only
when playback acquired the pause.

`recs profile` manages named saved recording setups. The `--profiles` option
instead reads a JSON file containing defaults for individual devices.

Inspect, validate, explain, and export recordings without starting the
recorder:

```console
recs sessions /path/to/recordings
recs session show /path/to/session
recs session quality /path/to/session
recs session quality /path/to/session --analyze-audio --json
recs record check /path/to/session/recording.toml
recs explain /path/to/session/session-record.jsonl
recs session export /path/to/session/recording.toml /path/to/export
recs session export-midi /path/to/session/recording.toml midi:Launchkey take.mid
```

`session export` verifies sealed source documents and their assets, copies into
a staging directory, then publishes the destination only after verifying all
copied assets. An interrupted copy retains its staging directory and reports
the path. Resume explicitly with the same source and destination:

```console
recs session export /path/to/session/recording.toml /path/to/export --resume /path/to/.export.recs-export-EXAMPLE
```

Resume requires the original source documents and media to remain available and
unchanged. It rechecks completed staged files before reuse and restarts partial
files from the beginning. A changed document, corrupt completed copy, or existing
destination is refused. No originals or partial directories are deleted.
`export-progress.json` lists files copied in this attempt, previously completed
files verified for reuse, remaining files, and failed files. The terminal reports
these counts on success or the failed item on interruption. If a disconnected or
full disk prevents saving progress, resume uses the last successfully saved report.
This is a local, single-worker copy; do not run concurrent resumes on one staging
directory. Moving the final directory does not depend on the original paths in
the progress report.

`session quality` reports one document's source-local captured durations, explicit
gaps, unfinished files, unresolved placement, and journal diagnostics. It does
not follow continuation documents or hash media. Intentional silence suppression
and discarded short captures are informational; known loss and incomplete
evidence are warnings. Unreadable documents, journals, or analyzed audio produce
errors and exit status 1. Advisories and warnings alone do not fail the command.

Audio analysis is opt-in and reads blocks of at most 48,000 frames. By default it
measures the first 60 seconds of each fragment and retains up to 100
near-full-scale runs per channel. Configure these limits with
`--analysis.max-seconds` and `--analysis.max-runs`; omitted frames/runs are reported.
`--analysis.near-full-scale-dbfs` defaults to −0.1 dBFS. These advisories do not
prove clipping, and quiet channels receive measured peak/RMS levels, not a
“bad microphone” verdict. Peak/RMS use normalized linear amplitude, with 1 as
full scale. Run ranges are half-open and clipped to the analyzed range.
Unmapped audio retains asset offsets without invented source positions. The
report never changes the recording; use `record check` for full media integrity.

Search the session library without decoding media:

```console
recs sessions /path/to/recordings --source x18 --marker solo --media audio --limit 20
recs sessions /path/to/recordings --since 2026-09-01 --before 2026-10-01 --incomplete --json
recs sessions /path/to/recordings --warning "offline"
```

Filters combine with AND. `--source`, `--track`, `--marker`, and `--warning`
use case-insensitive substring matching. Tracks include their source prefix;
marker text includes journal labels and pressed keys. `--warning ""` matches any
warning. Dates use the capture timestamp's recorded calendar date, not the file
modification time or a conversion to another timezone. `--since` is inclusive,
`--before` exclusive; unknown dates do not match date filters. `--incomplete`
includes open documents and unresolved audio placement. Captures without a
`recording.toml` remain outside this document-based library.

Results include matching reasons and use deterministic path order. The default
limit is 100; additional matches and unreadable documents are reported to stderr,
including with JSON output. A malformed document does not hide healthy sessions.
Search reads metadata and journals afresh, so moving a library needs no reindexing.

List markers, preview an extraction, then render it into a new session:

```console
recs session markers /path/to/session
recs session extract /path/to/session --clock clock-EXAMPLE --start-marker 1 --end-marker 2
recs session extract /path/to/session --clock clock-EXAMPLE --start-marker 1 --end-marker 2 --destination /path/to/extracted
```

Use the clock ID and numbered markers shown by `session markers`; repeated labels
are deliberately not selectors. `--tracks` restricts extraction to exact stream
IDs on that clock; otherwise all its audio streams are selected. For a passage
around one marker, omit `--end-marker` and provide `--lead` and/or `--tail` in
seconds. Durations round once to source frames; lead/tail are trimmed to the
common selected-track extent. Preview JSON (`--json`) includes requested and
resolved half-open frame ranges and the original marker evidence.

New explicit marks anchor to the latest processed block boundary received from
each active source. They do not claim the sample at button-press time: backlog
can make those anchors older. Historical marks and keyboard events without frame
evidence remain listable but cannot be extracted automatically. Independent
capture clocks, including reconnects, are never aligned by this command.

Extraction requires a sealed, mapped recording with full-channel output ports.
It writes float32 WAV tracks, `edit.toml`, and the usual recording/journal files,
with marker provenance in the `edit_started` entry. Gaps render as silence under
the existing renderer's rules. Original files are not rewritten, destinations
inside the original session are refused, and existing destinations are not reused.

Export aligned tracks for another editor:

```console
recs session handoff /path/to/session --clock audio:device --start-frame 0 --end-frame 480000
recs session handoff /path/to/session --clock audio:device --start-frame 0 --end-frame 480000 --destination /path/to/handoff
```

The preview is read-only. Rendering creates equal-length 32-bit float WAVs with
a shared source-frame origin and a JSON sidecar preserving track identities,
channel order, gap reasons, and applicable markers. Only one sealed, unlinked
segment and one capture clock are supported; no cross-device alignment is inferred.
See [Aligned track handoff](doc/track-handoff.md) for the sidecar contract.

Preview recovery of a stopped, interrupted capture, then create a separate copy:

```console
recs session recover /path/to/interrupted --json
recs session recover /path/to/interrupted --destination /path/to/recovered
```

Recovery verifies journal-referenced media in one version 4 capture segment.
Completed files with valid native timing become ordinary streams. Readable audio
without completion evidence is copied as unplaced assets, listed in
`recovery-report.json` without invented ranges or output ports. Missing, invalid,
ambiguous, and unsupported unfinished event files are explicitly omitted.
Intentional discards remain discards. Continuations and unreferenced files are
not scanned. A torn final JSON line is supported; interior journal corruption
requires separate investigation.

The original journal is preserved byte-for-byte under `evidence/`; media bytes
are unchanged. A new operation journal and sealed `recording.toml` describe the
recovered subset. Sealing means the recovery completed, not that the original
capture was complete. Original timestamps remain in the preserved evidence;
the new header/footer describe the recovery operation.

Recovery writes to a staging directory beside the destination, verifies the
copy, and only then publishes it. Failures leave originals unchanged and report
the retained partial directory. Existing destinations and destinations inside
the original session are refused. Stop capture before inspection or recovery;
changed evidence causes recovery to fail rather than silently use another version.

`recs edit` reads TOML edit definitions or installed edit commands and writes a
new session directory containing generated media, the resolved `edit.toml`, and
a new `recording.toml` and capture journal. Each installed edit command provides
Tyro-generated `--help`.

Offline edits decode, mix, normalize, hash, and encode audio in blocks of at most
65,536 frames. Prepared sources and intermediate results use temporary float32
backing files, preserving the prepared snapshot without lossy intermediate
encoding. RAM use scales with graph width and block size, not recording duration.
Temporary storage can require four bytes per sample per channel for each live
source or output; sparse timeline gaps may use less physical disk space. Files
are released with their prepared audio objects, including shared channel views.
`--dry-run` plans from metadata without rendering sources or intermediates.
Ordinary edit previews remain TOML, with resource estimates in comments;
composition previews describe stages and their estimates. Calibration previews
report audio-dependent results as unknown rather than running analysis.
Use `--scratch-directory /existing/directory` on an edit invocation to place all
its temporary audio there. The default remains the system temporary directory;
capture settings are unchanged. Space checks count full logical storage without
assuming sparse-file savings and combine scratch and known output requirements
when they share a filesystem. Estimates exclude interpreter and codec overhead,
do not predict compressed sizes, and cannot reserve disk capacity.
See [Edit resource planning](doc/edit-resources.md) for the assumptions and limits.

Older sessions require explicit conversion with `recs session migrate` before
editing or export. See [Recording and Sequence Scores](doc/recording-format.md)
for conversion, verification, and historical timing limitations.

After its live status publisher starts, recs checks its target-local recovery
worklist for unfinished sessions. A recording root is recursively discovered once per
filesystem, and each new or changed unresolved session receives a
`recs-recovery-report.toml` beside its session record and one logged summary.
Unchanged historical sessions are not rewritten or reported again. Use
`recs session recover-scan ROOT` to deliberately discover sessions copied into
an already-known recording root.

Recsam provides Pydantic models for the recs sample-instrument format and SFZ
import/export with explicit reporting of unsupported features. Audio playback
of Recsam instruments is not implemented yet.

## Reference Documentation

- [Glossary](doc/glossary.md)
- [Runtime Architecture](doc/runtime-architecture.md)
- [Session Directory](doc/session-directory.md)
- [Recording and Sequence Scores](doc/recording-format.md)
- [Audio Arrangement Scores](doc/arrangement-format.md)
- [recs Protocol](doc/recs_protocol.md)
- [Configuration Units](doc/configuration-units.md)
- [Sample Instrument Scores](doc/sample-format.md)

Current unfinished design work is kept under `plan/`. Historical reviews and
completed plans are deliberately not retained as product documentation.
