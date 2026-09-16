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
recs record check /path/to/session/recording.toml
recs explain /path/to/session/session-record.jsonl
recs session export /path/to/session/recording.toml /path/to/export
recs session export-midi /path/to/session/recording.toml midi:Launchkey take.mid
```

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
The system temporary directory must have enough space. Composition summaries
distinguish temporary audio storage from estimated audio-buffer memory; these
estimates exclude interpreter, graph metadata, and codec overhead.

Older sessions require explicit conversion with `recs session migrate` before
editing or export. See [Recording and Sequence Scores](doc/recording-format.md)
for conversion, verification, and historical timing limitations.

Before opening a new record, recs scans the configured output root for
unfinished sessions. Each one receives a `recs-recovery-report.toml` beside its
session record, and recs logs a one-line summary with the report path.

Recsam provides Pydantic models for the recs sample-instrument format and SFZ
import/export with explicit reporting of unsupported features. Audio playback
of Recsam instruments is not implemented yet.

## Reference Documentation

- [Glossary](doc/glossary.md)
- [Runtime Architecture](doc/runtime-architecture.md)
- [Session Record Format](doc/session-record-format.md)
- [Recording and Sequence Scores](doc/recording-format.md)
- [Audio Arrangement Scores](doc/arrangement-format.md)
- [recs Protocol](doc/recs_protocol.md)
- [Configuration Units](doc/configuration-units.md)
- [Sample Instrument Scores](doc/sample-format.md)

Current unfinished design work is kept under `plan/`. Historical reviews and
completed plans are deliberately not retained as product documentation.
