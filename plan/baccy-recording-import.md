# Import older recordings into recs sessions

## Goal

Import the non-MP3 recordings under
`/Users/tom/Documents/Work/import into baccy` into valid, sealed recs session
directories for the two supplied projects: `totm` and `oderg in duo`.

The importer must preserve every source recording unchanged, create a normal
`recording.toml` for each imported session, and make every inferred detail
traceable. It must not claim that reconstructed timestamps, stream names, or
frame positions were observed by the original recorder.

This plan is based on the supplied project names. The current environment is
not permitted to read the Documents directory, so the implementation begins
with an inventory rather than assuming its present filenames or hierarchy.

## Ownership and interface

Put the one-shot script in `scripts/import_baccy_recordings.py` in recs. It
uses recs' session-record and finalization code directly, avoiding a duplicate
recording-writer implementation or a new baccy dependency on recs internals.

The command takes:

```text
scripts/import_baccy_recordings.py SOURCE_ROOT DESTINATION_ROOT --project PROJECT
```

It accepts only `totm` or `oderg in duo` as `PROJECT` for this import. A
mandatory `--dry-run` prints the proposed source-to-session mapping and all
synthetic values. A separate `--write` is required to create output. The script
never renames, deletes, or writes beneath `SOURCE_ROOT`, and ignores every
file whose suffix is `.mp3` case-insensitively.

`DESTINATION_ROOT` remains explicit because this plan does not establish where
baccy should keep imported sessions. The resulting session layout is:

```text
DESTINATION_ROOT/
  totm/
    YYYY/MM/DD/HH-MM-SS/
      session-record.jsonl
      recording.toml
      audio/...
  oderg in duo/
    YYYY/MM/DD/HH-MM-SS/
      ...
```

The project directory name and `body.project_name` are exactly the selected
project name. A collision uses recs' normal `_1`, `_2`, and later suffixes;
the importer never overwrites an existing session.

## Discovery and grouping

1. Recursively inventory `SOURCE_ROOT`, excluding MP3 files before any other
   classification. Report unsupported non-MP3 files and leave them untouched.
2. Recognize finite audio files supported by `soundfile`, recording their
   format, sample rate, channel count, and frame count from the decoded file
   metadata. Refuse a file that `soundfile` cannot inspect rather than writing
   a false audio record.
3. Require the caller to select one supplied project per run. Do not infer a
   project from a parent directory name, because that inference would silently
   misfile material when the source hierarchy changes.
4. Start conservatively with one source audio file per session. This guarantees
   that unrelated takes cannot be merged merely because their modification
   times are close. Add explicit `--group FILE ...` arguments only if the
   inventory shows known multitrack take groups that need one session.
5. Derive the session date and time from the source file's modification time in
   the local timezone. This is synthetic organizational metadata, not an
   original capture timestamp. The dry run prints it for review before output
   is created.

## Constructing a session

For every selected input group:

1. Copy source files into a fresh staging directory under `DESTINATION_ROOT`.
   Preserve their bytes and suffixes. Calculate SHA-256 and compare it with the
   copied result before publication.
2. Write a version 4 `session-record.jsonl` with a new deterministic session
   ID derived from the project name and imported content hashes. Set
   `project_name` to the selected project, and add header metadata containing
   the original source path relative to `SOURCE_ROOT`, original modification
   timestamp, and `imported = true`.
3. For each copied audio file, write matching `file_started` and
   `file_finished` records using facts from the file metadata: actual format,
   channel count, sample rate, frame count, and a single audio span from native
   frame zero through the complete file. Use a distinct opaque stream ID per
   file. Use a neutral source name based on the filename stem and one track
   containing all source channels. These stream labels and native frame zero
   are reconstructed conventions, not facts about the old hardware capture.
4. Use the selected source file's synthetic timestamp for the session header
   and footer, with duration derived from `frames / sample_rate` when the file
   has audio. Record the same convention in header metadata. Do not create
   clock observations, dropped-frame events, silence-suppression gaps, MIDI,
   OSC, key, musician, or continuation records, because the source files do
   not establish them.
5. Finalize with `recs.recording.finalize.finalize_recording`, producing the
   standard sealed `recording.toml` with `body.project_name`. Validate it with
   the existing session-record checker and audio verification before moving
   staging into its final date/project directory atomically.
6. Print a concise import report with each source path, target session path,
   SHA-256, synthetic timestamp, and any unsupported files. A failed group
   leaves its source untouched and its staging directory unpublished.

## Tests and acceptance

Create small WAV fixtures for both projects plus an MP3-named sentinel and an
unsupported non-MP3 file. Tests must prove that:

- dry run writes no files and reports the planned mapping;
- MP3 files are neither copied nor reported as failed audio;
- each accepted audio file is copied byte-for-byte into the selected project's
  session directory;
- the journal and finalized `recording.toml` have the exact selected
  `project_name` and a valid sealed asset reference;
- `recs session check` and `verify_recording` accept every generated session;
- source paths, original modification timestamps, and the synthetic-timing
  convention are preserved in journal metadata;
- same-second imports create separate suffixed session directories without
  altering prior output; and
- an unreadable or unsupported input causes no published partial session.

Run the dry run against the real folder first and review its mapping before the
single `--write` invocation. After import, compare the reported source hashes
with the copied files and keep the original folder until baccy has separately
backed up and verified the new sessions.

## Additional work beyond the prompt

None.
