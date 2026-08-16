# Feature proposal: session manifests

`recs` already solves the hardest part of recording: it can sit in the
background, watch many inputs, ignore quiet, and write usable audio files
without asking the user to press a record button at the right moment. A useful
next feature would be a session manifest: a small machine-readable file written
next to the recordings that describes what happened during one invocation.

The manifest would not replace audio metadata. Audio metadata is tied to a
single file and is limited by what each format supports. A manifest can describe
the whole recording session, including files, devices, channels, timestamps,
configuration, and warnings. The natural format is JSON because `recs --info`
already emits JSON and many downstream tools can read it.

For each run, `recs` could write something like `recs-session.json` in the
output directory. If several sessions write to the same directory, the manifest
could use the same timestamp or collision-avoidance naming rules as audio files.
The file should be written incrementally or finalized safely during shutdown,
so it remains useful after Ctrl-C or a normal termination signal.

The manifest should answer practical questions a user will have later:

- Which device and channel produced this file?
- What start and end time does the session cover?
- What sample rate, bit depth, subtype, and channel layout were used?
- What include and exclude rules selected these tracks?
- Were any devices offline, restarted, too slow, or unavailable?
- Did `recs` delete any too-short files?
- What command-line options affected this session?

A minimal first version could record only stable, high-value data:

```json
{
  "started_at": "2026-06-20T18:00:00Z",
  "ended_at": "2026-06-20T18:42:17Z",
  "duration": 2537.0,
  "files": [
    {
      "path": "files/mono-1.wav",
      "source": "input/mono.wav",
      "track": 1,
      "channels": 1,
      "sample_rate": 48000,
      "bit_depth": 32
    }
  ],
  "events": [
    {
      "timestamp": "2026-06-20T18:00:03.000Z",
      "type": "source_online",
      "source": "Mic"
    },
    {
      "timestamp": "2026-06-20T18:00:04.000Z",
      "type": "track_started",
      "source": "Mic",
      "track": "1"
    },
    {
      "timestamp": "2026-06-20T18:12:33.000Z",
      "type": "track_stopped",
      "source": "Mic",
      "track": "1"
    },
    {
      "timestamp": "2026-06-20T18:14:02.000Z",
      "type": "source_offline",
      "source": "Mic"
    }
  ],
  "warnings": [
    "Device Mic lagging behind real time"
  ]
}
```

This is especially useful for long-running and unattended recording. Today, the
file name carries a lot of meaning, but the filename is still optimized for
humans. A manifest lets software reconstruct the session without parsing names.
That makes it easier to import files into a DAW, build a web index, generate
cue sheets, diagnose missing audio, or sync recordings against notes taken
during the session.

The feature also gives `recs` a clean place to expose operational facts that do
not belong in the audio stream. For example, device lifecycle events could be
captured as structured records instead of only terminal messages. A user could
later see that a USB interface disappeared at 18:12 and returned at 18:14, or
that a source was stopped because it lagged behind real time. That is valuable
when `recs` is used as a safety recorder, where knowing why a file is missing
can matter as much as the file itself.

The manifest should also record the two lifecycle streams that explain gaps in
the resulting files. Source events describe when a device or file source became
available or unavailable during the session. Track events describe when an
individual track actually started or stopped writing audio after quiet filtering.
Keeping both levels matters because they answer different questions: a device
can stay online while one track is quiet, and a track can stop because the
device disappeared. A minimal event schema only needs a timestamp, an event
type, a source name, and, for track events, the track name.

The implementation should stay small. The main recorder already knows about
files written, sources, elapsed time, failures, and warnings. The first version
can collect these facts in the main process and write one JSON file at summary
time. Later versions could add richer per-file timing, deleted-file records,
and optional append-only event logging, but the initial feature should avoid
becoming a database or project format.

The success criterion is simple: after a recording session, a user should be
able to hand someone the audio files plus the manifest and have them understand
what was recorded, where each file came from, and whether anything unusual
happened.
