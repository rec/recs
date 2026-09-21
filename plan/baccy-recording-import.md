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

The importer must create the new session metadata immediately, preserve actual
audio facts, and mark every reconstructed field as inferred. It must never
overwrite or modify the input tree. It does not move media itself.

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

The command immediately creates the new session directories, journals, and
`recording.toml` files. It hashes the source media and writes score asset
locations for the media's future `audio/` or `evidence/` paths.

It then prints quoted Bash `mv -n` commands that will move each source media or
LiveTrak evidence file to that already-created destination. The commands are
not run by the script. They are the separate, user-controlled rearrangement
step. It also prints later `recs session check` and SHA-256 verification
commands. A same-second collision uses the normal `_1`, `_2`, and later
suffixes. There is no move, rename, deletion, or write below `SOURCE_ROOT`.

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
`soundfile`, then calculate its source SHA-256 and byte length. Write that
identity and the planned relative `audio/` path into the new score. Use the
file's true native frame count and a complete span starting at frame zero.
Frame zero is a reconstructed per-file timeline convention, not a claim of
cross-device synchronization.

Header metadata records `imported = true`, the path relative to
`SOURCE_ROOT`, the grouping rule, timestamp source, source SHA-256, and that
the media relocation is pending. Do not invent clock observations, dropped-frame
events, silence-suppression gaps, musicians, MIDI events, OSC events, key
events, or continuations.

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
   input-channel assignment. Plan its `PRJDATA.ZDT` move to `evidence/` and
   list it in the journal metadata as unparsed device evidence.
4. **Existing recs session.** The 4 September 2026 `oderg in duo` directory
   contains a version-3 journal and version-3 `recording.toml`. Read and
   migrate that evidence while it remains at its source path. Write its v4
   destination metadata immediately, with `body.project_name = "oderg in duo"`
   and planned relative asset paths. Print moves for the original journal,
   v3 TOML, MIDI, and audio into their destination evidence/media paths.

Ignore every MP3. Also exclude `.DS_Store`, `.Spotlight-V100`, `.fseventsd`,
and `.reapeaks` from sessions as operating-system or rebuildable editor data.
Report these exclusions. Reject other unknown non-audio files unless they are
the identified LiveTrak `PRJDATA.ZDT` evidence.

## Immediate metadata publication and later relocation

1. Build the journal and score under a private staging sibling of its final
   directory. The score is written directly from source metadata and hashes,
   not through `finalize_recording`, because its referenced media has not moved
   yet.
2. Validate the journal and parse the staged `recording.toml`; reject malformed
   source audio, source-hash failures, and invalid score data before publication.
   Do not run payload verification while planned media paths are empty.
3. Atomically publish the metadata-only session directory. Never reuse an
   existing destination.
4. Print shell-quoted `mv -n SOURCE DESTINATION` statements for every planned
   audio, MIDI, journal-evidence, and `PRJDATA.ZDT` relocation. Print the
   corresponding `shasum -a 256` and `recs session check` commands after each
   group's moves. The script does not invoke a shell or execute any printed
   statement.
5. Print a final summary of created sessions, duplicate/skipped groups, and
   rejected inputs. The output is the relocation plan, not capture evidence.

## Tests and acceptance

Create minimal fixtures for a FLOW 8 five-pair take, a microphone addition, a
LiveTrak project with mono/pair/master tracks and `PRJDATA.ZDT`, matching and
non-matching copy trees, a v3 recs session, MP3 and macOS/editor exclusions,
and a corrupt WAV.

- One invocation creates schema-valid metadata-only sessions and prints the
  complete, non-executed media-relocation command sequence.
- Each source family produces the specified grouping and exact project name in
  both journal and `recording.toml`.
- Generated scores retain source hashes, actual audio metadata, and frame
  counts while their planned media paths are empty.
- After executing the printed moves, every target media file hash matches its
  score asset and the printed `recs session check` command passes.
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
