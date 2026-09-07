# recs: the Universal Recorder

Recs continuously records audio, MIDI, OSC, and key events into timestamped
sessions. Audio can be recorded continuously or split around quiet passages.
Each completed session has a `recording.toml` indexing its media and native
timelines. Its `session-record.jsonl` preserves capture lifecycle, source,
configuration, disk, and control events.

The recorder is designed to run unattended. It discovers selected audio and
MIDI devices after startup, resumes when devices return, monitors free space,
and can continue a session on another removable disk.

## Requirements And Installation

Recs requires Python 3.13 or newer and the system libraries required by
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

Run Recs with no arguments to record available audio inputs in the current
directory:

```console
recs
```

By default, Recs records audio as FLAC, records MIDI inputs, and omits quiet
audio between files. A run creates a timestamped session directory:

```text
2026-09-07 20-15-15/
  recording.toml
  session-record.jsonl
  audio/
    1-2 + 20260907-201515.flac
  midi/
    Launchkey-20260907-201515.mid
  osc/
    X18.jsonl
```

Select inputs and an output root with ordinary recording options:

```console
recs --include xr18 --output-directory /mnt/openloop/recs
```

The output directory is the root for sessions. Recs computes each session
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

Recs can install and manage a per-user background service:

```console
recs daemon install --output-directory /mnt/openloop/recs
recs daemon status
recs daemon restart
recs daemon stop
recs daemon uninstall
```

Inspect and control a running daemon locally:

```console
recs watch
recs control status
recs control disk
recs control mark "solo starts"
recs control pause
recs control resume
recs control card-replace
```

The complete local RPC and event interface, including live waveforms and the
`new_session` command, is documented in [Recs Protocol](doc/recs_protocol.md).

## Sessions And Editing

Inspect, validate, explain, and export recordings without starting the
recorder:

```console
recs sessions /path/to/recordings
recs session show /path/to/session
recs record check /path/to/session/recording.toml
recs explain /path/to/session/session-record.jsonl
recs session export /path/to/session/recording.toml /path/to/export
```

`recs edit` reads TOML edit definitions or installed edit commands and writes a
new session directory containing generated media, the resolved `edit.toml`, and
a new `recording.toml` and capture journal. Each installed edit command provides
Tyro-generated `--help`.

Older sessions require explicit conversion with `recs session migrate` before
editing or export. See [Recording and Sequence Documents](doc/recording-format.md)
for conversion, verification, and historical timing limitations.

Before opening a new record, Recs scans the configured output root for
unfinished sessions. Each one receives a `recs-recovery-report.toml` beside its
session record, and Recs logs a one-line summary with the report path.

Recsam provides Pydantic models for the Recs sample-instrument format and SFZ
import/export with explicit reporting of unsupported features. Audio playback
of Recsam instruments is not implemented yet.

## Reference Documentation

- [Glossary](doc/glossary.md)
- [Runtime Architecture](doc/runtime-architecture.md)
- [Session Record Format](doc/session-record-format.md)
- [Recording and Sequence Documents](doc/recording-format.md)
- [Audio Arrangement Documents](doc/arrangement-format.md)
- [Recs Protocol](doc/recs_protocol.md)
- [Configuration Units](doc/configuration-units.md)
- [Recsam Instrument Format](doc/sample-format.md)

Current unfinished design work is kept under `plan/`. Historical reviews and
completed plans are deliberately not retained as product documentation.
