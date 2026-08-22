# New Feature Suggestions

## Scope

This document suggests future `recs` features. It favors features that make the
recorder safer to run unattended, easier to inspect after a session, and more
useful as a local service. It does not include refactoring work from
`plan/possible-issues.md` unless that refactoring directly unlocks a user-facing
feature.

Existing plans already cover external IPC, disk-space handling, daemon install,
Raspberry Pi operation, calibration, and the remote GUI. Those ideas are
included here only where they need product-level prioritization or where a
smaller feature could land first.

## Priorities

1. Protect recordings and make failures visible.
2. Make unattended daemon operation trustworthy.
3. Improve session review and file recovery.
4. Add control features that reduce setup time at a show.
5. Explore larger "universal recorder" directions only after the audio recorder
   is operationally solid.

## Daemon and control features

### Local web control panel

Provide a small local web UI for daemon status and common controls:

- recording health;
- device and track status;
- disk status;
- current output directory;
- recent warnings;
- calibrate;
- mark;
- pause, resume, and stop recording;
- safe shutdown.

Why it matters: the Raspberry Pi stage-recorder workflow needs phone or tablet
control without requiring SSH or a desktop GUI.

Implementation notes: build this on the documented RPC protocol. Keep it
optional and separate from the recording process so UI failures cannot stop
recording.

### Dedicated hardware or USB command trigger

Support a simple physical command path for unattended rigs. Examples:

- insert a USB stick with a command file to trigger calibration or shutdown;
- press a configured keyboard key to add a labeled marker;
- press a simple GPIO button on Raspberry Pi for mark or safe shutdown.

Why it matters: a stage recorder may run without a monitor, keyboard, or network.

Implementation notes: keep the first version narrow. A USB command file or
existing keyboard path is less invasive than adding GPIO dependencies.

### Control API client CLI

Add commands that send one RPC request to the running daemon:

```sh
recs control mark "solo starts"
recs control calibrate
recs control set recording.longest_file_time 3600
recs control pause
recs control resume
```

Why it matters: shell scripts and other local tools should not need to construct
JSON envelopes for common operations.

Implementation notes: use the existing public RPC endpoint and protocol models.
Do not call daemon internals directly.

### Status monitors

Add watch-style commands:

```sh
recs watch
recs watch --json
```

Useful modes:

- live rows, similar to the terminal UI;
- warnings only;
- disk countdown;
- device online/offline changes;
- buffer pressure and dropped frames.

Why it matters: this gives a terminal-friendly view of a daemon without starting
a second recorder.

Implementation notes: subscribe to events rather than polling aggressively.

## Recording workflow features

### Setup profiles

Add named setup profiles that group device selection, track layouts, aliases,
noise floors, formats, output directory patterns, and marker labels:

```sh
recs profile save rehearsal
recs profile use x18-show
recs daemon install --profile x18-show
```

Why it matters: the same user may move between laptop microphone, USB interface,
X18, cassette digitizing, and stage-recording setups. Device profiles already
exist, but users need a higher-level setup unit.

Implementation notes: avoid adding another partial config format unless it can
round-trip through the existing `Cfg` model.

### Guided calibration workflow

Build a command and control API flow that measures selected tracks, previews
recommended noise floors, and optionally applies them:

```sh
recs calibrate --interactive
recs control calibrate --apply
```

Useful behavior:

- choose all selected tracks by default;
- allow a subset of tracks;
- show measured values and previous values;
- apply per-track noise floors;
- write a manifest event when calibration changes live recording state.

Why it matters: noise-floor setup is one of the most important quality knobs and
one of the easiest to get wrong.

Implementation notes: keep quiet-before and quiet-after as user-selected timing
settings. Calibration should tune noise floors, not rewrite all silence
behavior.

### Track layout presets

Allow a named track layout to be saved and reapplied:

```sh
recs tracks save x18-stereo-pairs
recs tracks use x18-stereo-pairs
```

Why it matters: multi-channel interfaces often have stable routing. Rebuilding
mono and stereo pairs through the GUI or protocol is repetitive.

Implementation notes: validate layouts against the currently detected channel
count before applying them. If a layout cannot apply cleanly, fail loudly rather
than partially changing tracks.

### Session marker improvements

Expand markers beyond plain labels:

- marker categories;
- quick marker keys;
- start and end markers for sections;
- optional notes;
- marker export as CSV or JSON.

Why it matters: markers turn long unattended recordings into usable session
material.

Implementation notes: keep the manifest event format append-only and simple.
Avoid adding editing semantics until there is a session browser.

## Recovery and export features

### Session package export

Add a command that copies a session manifest and all referenced files into a
portable folder:

```sh
recs session export PATH/to/recs-session.jsonl DEST
```

Useful behavior:

- preserve relative track paths where possible;
- include continued manifests after disk switches;
- write an export summary;
- optionally verify file sizes after copy.

Why it matters: recordings often need to move from a stage disk to a laptop or
archive disk without losing manifest context.

Implementation notes: keep export read-only relative to the original session.

### Split and stitch tools

Add post-processing commands based on manifest timing:

```sh
recs session split PATH --markers
recs session stitch PATH --track "1-2"
```

Use cases:

- export one continuous WAV per track;
- cut files by markers;
- gather all files for one song or set;
- repair a session split across disks.

Why it matters: `recs` creates capture-oriented files. Users often need
review-oriented files afterward.

Implementation notes: this can be CPU and disk intensive. It should be an
explicit post-processing command, not part of live recording.

### Recovery report after abnormal exit

On the next start, detect an unfinished previous manifest and offer a report:

- last known source updates;
- files that were open;
- files that exist but have no final manifest event;
- disk status at last event;
- likely completeness of each track.

Why it matters: a power loss or crash should leave the user with a clear damage
assessment.

Implementation notes: do not mutate old manifests in the first version. Produce
a report beside the manifest if persistence is needed.

## Longer-term universal recorder features

### DMX and lighting event recording

Record DMX, Art-Net, sACN, or related lighting-control streams as timed data.

Why it matters: this fits the broader live-show recording goal and can share the
manifest/session model.

Implementation notes: treat this as a separate protocol source with its own
storage format. Avoid coupling it to audio tracks or channel writers.

### Companion player

Add a read-only player that can play a session timeline:

- audio files;
- markers;
- future MIDI or lighting streams;
- disk-switch continuity.

Why it matters: capture is only half the recorder story. A timeline player makes
the recorded data useful without requiring manual file hunting.

Implementation notes: this should come after the manifest index and validation
commands so playback has a reliable source of truth.

## Features to avoid for now

### Embedded Twitch streaming

Do not put Twitch streaming inside the recorder process. The performance plan
already argues for a separate streamer so network and encoder failures cannot
block local recording.

### Live video capture

Avoid live video capture in `recs` for now. It conflicts with the goal of a
lightweight background recorder and adds large CPU, disk, and synchronization
problems.

### Database-backed session history

Do not add a database until manifest scanning is proven insufficient. JSONL
manifests are easier to inspect, copy, recover, and test.

### Complex automatic editing

Avoid features that automatically decide song boundaries, remove silence
destructively, normalize audio, or publish mixes from live recordings. Those are
post-processing concerns and should not add risk to capture.

## Suggested first implementation order

1. `recs control ...` RPC client commands
2. local web control panel
3. session export
4. guided calibration workflow

## Additional work beyond the prompt

None.
