# Import `import into baccy` recordings into recs sessions

## Goal

Import the non-MP3 recordings in the repository-top-level
[`import into baccy`](../import%20into%20baccy) directory into valid, sealed
recs sessions. The two destination projects are exactly `totm` and
`oderg in duo`.

The source contains three distinct forms of capture:

- `oderg in duo` has grouped five-pair FLOW 8 WAV takes below dated,
  time-named directories, a duplicate `15-33-15 copy` take, and one version-3
  recs session from 4 September 2026.
- `totm/FLOW 8` has date directories whose WAV filenames contain a time and
  channel-pair label, plus some MacBook microphone WAV files.
- `totm/LiveTrak L-12` has 35 LiveTrak project directories named
  `YYMMDD_HHMMSS`, containing `TRACK*.WAV`, occasional `MASTER.WAV`, and
  `PRJDATA.ZDT` device metadata.

The importer must copy source recordings unchanged, preserve actual audio
facts, and mark every reconstructed field as inferred. It must never overwrite
or modify the input tree.

## Ownership and interface

Put the one-shot script in `scripts/import_baccy_recordings.py` in recs. It
uses recs' session-record and finalization code directly, rather than creating
a duplicate writer in baccy.

```text
scripts/import_baccy_recordings.py SOURCE_ROOT DESTINATION_ROOT
```

The caller passes the `import into baccy` directory as `SOURCE_ROOT` and an
explicit, initially empty session root as `DESTINATION_ROOT`. The script maps
the top-level `totm` and `oderg in duo` directories to those exact recs project
names. It rejects an unknown top-level project instead of guessing.

The command creates and validates sessions directly. As it does so, it prints
Bash-equivalent `mkdir`, `cp`, hash-check, and publish commands for every
proposed filesystem operation, including source groups, destination paths,
timestamp sources, duplicate findings, and exclusions. Those lines are an audit
log only: the script never invokes a shell or executes its printed commands.
It creates only new directories. A same-second collision uses the normal `_1`,
`_2`, and later suffixes. There is no move, rename, deletion, or write below
`SOURCE_ROOT`.

## Session reconstruction rules

The generated layout is:

```text
DESTINATION_ROOT/
  totm/YYYY/MM/DD/HH-MM-SS/
  oderg in duo/YYYY/MM/DD/HH-MM-SS/
```

Every new journal is version 4 and includes its exact `project_name`; its
finalized `recording.toml` therefore has the same `body.project_name`.

For each imported audio file, read format, rate, channels, and frame count with
`soundfile`. Copy bytes into `audio/`, hash source and destination, and refuse
to publish a group unless hashes match. Use the file's true native frame count
and a complete span starting at frame zero. Frame zero is a reconstructed
per-file timeline convention, not a claim of cross-device synchronization.

Header metadata records `imported = true`, the path relative to
`SOURCE_ROOT`, the grouping rule, timestamp source, and source SHA-256. Do not
invent clock observations, dropped-frame events, silence-suppression gaps,
musicians, MIDI events, OSC events, key events, or continuations.

The session ID is deterministic from project name and sorted source hashes, so
a dry-run/report can identify the same proposed import. Wall timestamps use the
date/time encoded by the source path or filename, not filesystem modification
time. They include `timing_source = "source_name"` in header metadata because
the source's timezone and clock accuracy are unknown.

## Source-family grouping

1. **FLOW 8 pair takes.** Group files sharing one project, calendar date, and
   six-digit take time. Parse labels such as `1-2 + 142131` as channel pairs
   `[1, 2]`; retain `FLOW 8` or `MacBook Pro Microphone` as the source name.
   The five same-time FLOW 8 pairs become one session with five streams. A
   microphone file at that same time becomes another stream in that session.
   A missing pair is valid evidence of a partial original take, not a reason to
   create silence.
2. **April duplicate.** Hash every source in `15-33-15` and `15-33-15 copy`.
   If all corresponding audio hashes match, import one session and report the
   second tree as a duplicate. If any differ, skip both groups and require an
   explicit selection flag. Never silently choose between non-identical takes.
3. **LiveTrak L-12 projects.** Each `YYMMDD_HHMMSS` project directory is one
   session. Interpret `YY` as `20YY`, retain `LiveTrak L-12` as source metadata,
   map `TRACK01` through `TRACK08` to their matching one-based channel labels,
   and map `TRACK09_10` and `TRACK11_12` to their two channel labels.
   `MASTER.WAV` is an additional `LiveTrak L-12 master` stream with no invented
   input-channel assignment. Copy `PRJDATA.ZDT` to `evidence/` and list it in
   the journal metadata as unparsed device evidence.
4. **Existing recs session.** The 4 September 2026 `oderg in duo` directory
   contains a version-3 journal and version-3 `recording.toml`. Copy its entire
   media and journal evidence to staging, preserve the old TOML under
   `evidence/recording-v3.toml`, run the existing explicit v3 migration, then
   set the migrated score's `body.project_name` to `oderg in duo` before writing
   the v4 `recording.toml`. Preserve the original journal under the migration
   evidence path required by the migration code.

Ignore every MP3. Also exclude `.DS_Store`, `.Spotlight-V100`, `.fseventsd`,
and `.reapeaks` from sessions as operating-system or rebuildable editor data.
Report these exclusions. Reject other unknown non-audio files unless they are
the identified LiveTrak `PRJDATA.ZDT` evidence.

## Publication and validation

1. Build each session under a private staging sibling of its final location.
2. Write the journal and call `finalize_recording` for reconstructed sessions.
   The legacy-recs path uses the existing migration function instead.
3. Run `session_record_check.check` and `verify_recording` on the staged score.
   Failure leaves no final session directory and records the reason in the
   command's report.
4. Atomically rename the completed staging directory to its final session path.
   Never reuse an existing destination.
5. Print a Bash-equivalent audit line before each source copy, staging-directory
   creation, hash check, and publication, and a final summary of imported,
   duplicate, skipped, and failed groups. The audit lines are never executed.

## Tests and acceptance

Create minimal fixtures for a FLOW 8 five-pair take, a microphone addition, a
LiveTrak project with mono/pair/master tracks and `PRJDATA.ZDT`, matching and
non-matching copy trees, a v3 recs session, MP3 and macOS/editor exclusions,
and a corrupt WAV.

- One invocation creates only validated sessions and prints the complete,
  non-executed Bash-equivalent audit trail.
- Each source family produces the specified grouping and exact project name in
  both journal and `recording.toml`.
- Audio copies hash-identically, retain their actual metadata and frame count,
  and pass recs session checking and recording verification.
- The matching April copy imports exactly once; a nonmatching copy publishes
  neither candidate without an explicit selection.
- Legacy migration preserves v3 evidence and produces a valid v4 score with
  `body.project_name = "oderg in duo"`.
- MP3, macOS metadata, Reaper peaks, and unsupported files are neither copied
  as audio nor allowed to create a partial session.
- Existing targets, copy failures, malformed timestamps, and corrupt audio
  leave all source and previously published output unchanged.

Keep `import into baccy` until baccy has separately backed up and verified the
new sessions.

## Additional work beyond the prompt

None.
