# Top Remaining Features

## Scope

This is the ranked product backlog for the five most valuable unfinished Recs
features. Completed work and ideas superseded by Showco or existing Recs tools
have been removed.

## 1. Portable Session Export

Add a read-only command that copies a session and every referenced continuation
record and media file into one self-contained directory:

```console
recs session export SESSION-RECORD DESTINATION
```

The export must rewrite record links and media paths relative to the exported
records, retain session IDs and provenance, verify copied file sizes, and write
an export summary. It must never modify its sources or leave a destination that
looks complete after a failed copy.

This is the highest-value remaining feature because sessions may span removable
disks and currently require manual copying without a reliable completeness
check.

## 2. Named Recording Setups

Add named setup profiles covering device selection, aliases, track layout,
noise floors, formats, output patterns, and marker labels:

```console
recs profile save rehearsal
recs profile use x18-show
recs daemon install --profile x18-show
```

Profiles should round-trip through the existing `Cfg` and track-settings models.
Applying a profile must validate its layout against detected hardware and fail
without partially changing the active setup.

This consolidates the narrower track-layout-preset idea and removes repetitive,
error-prone setup before recordings.

## 3. Daemon Status Watch

Add an event-driven terminal client for a running daemon:

```console
recs watch
recs watch --json
```

It should expose live recording rows, warnings, disk countdown, source
transitions, buffer pressure, dropped frames, and card-replacement state. It
must subscribe to public events rather than poll the recorder and must not start
another recording process.

This provides a lightweight diagnostic path when Showco is unavailable and is
especially useful over SSH.

## 4. SFZ Export

Implement deterministic best-effort serialization from recsam to SFZ, with
complete diagnostics for fields that SFZ cannot represent. A completely
imported SFZ file must survive recsam-to-SFZ-to-recsam conversion without losing
supported behavior or Recs metadata.

The detailed design and acceptance criteria are in [SFZ Export](sfz-write.md).
This closes the interoperability loop for existing sample libraries and makes
recsam safer to adopt as an editable intermediate format.

## 5. Offline Recsam Playback

Implement the recsam playback engine first as deterministic offline rendering
from performance events into a new Recs session. Establish slot selection,
voice lifecycle, timing, loops, envelopes, modulation, routing, and shared asset
loading before adding a live audio host.

The detailed design and hardware-validation boundary are in
[Sample Playback](sample-playback.md) and
[Human And Experimental Verification](human.md).

This turns recsam from a schema and converter into a usable instrument format
while keeping live latency and callback risk out of the first implementation.

## Additional Work Beyond The Prompt

None.
