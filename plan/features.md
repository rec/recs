# Feature proposals for recs

## Scope

Proposed 16 September 2026, against the current repository. Implementation status
is recorded under each feature; unmarked features remain proposals.
The focus is recording, reviewing, editing, recovering, and handing off captured
material. No changes to other projects are proposed.

recs already provides unattended capture, device reconnection, silence-aware
segmentation, saved setups, live control and waveforms, markers, session browsing,
integrity checks, recovery reports, playback, export, and bounded offline edits.
The proposals below extend those facilities rather than replace them.

Synth and sampler implementation, instrument authoring, streaming services,
lighting, show orchestration, plugin hosting, and general-purpose DAW features
are outside this document. See [plans and ownership](README.md).

## Suggested priority

| Order | Feature | Main benefit | Relative scope |
| --- | --- | --- | --- |
| 1 | Recording readiness report | Catch setup mistakes before capture | Small to medium |
| 2 | Session quality report | Find damaged or questionable passages quickly | Medium |
| 3 | Searchable session library | Find recordings without opening each session | Small to medium |
| 4 | Marker-based extraction | Turn remembered moments into useful clips | Medium |
| 5 | Assisted recovery into a new session | Recover usable material without modifying evidence | Medium to large |
| 6 | Resumable verified export | Avoid restarting a large copy after interruption | Medium |
| 7 | Aligned track handoff | Prepare recordings for an external editor | Medium |
| 8 | Edit resource planning | Make long renders predictable before they start | Small to medium |

Scope estimates are relative, not delivery promises. Start with readiness and
quality reporting: both improve confidence in the recorder without introducing
a new rendering engine or changing recorded media.

## 1. Recording readiness report

Implemented: `recs readiness`, with saved setups, mutable overlays, explicit
option overrides, text/JSON reports, and independent diagnostics. Missing devices
warn; invalid settings/channels/output paths fail. No capture streams, sessions,
or write probes are created. Alias targets that cannot currently resolve are
reported explicitly. MIDI/OSC availability is not probed.

Storage reporting uses a labelled continuous input-PCM equivalent estimate,
subtracting the minimum free-space reserve. It does not invent a compression
ratio or finite upper duration bound; actual compressed/silence-suppressed
duration remains unknown. Other disk policy and overhead are stated limitations.

Question answered: “Will this setup record the sources and tracks I intend?”

Existing foundation: device inspection, saved setups, resolved configuration,
disk monitoring, and the explicit input self-test. The new feature is a combined
explanation of one selected setup before starting capture, not another device
listing or an automatically triggered recording test.

First version:

- Show resolved devices, channel layouts, track names, formats, output root, and
  effective settings, including saved mutable overrides.
- Distinguish present sources, configured sources not currently present, and
  selectors that match nothing. Explain which omissions prevent the intended run.
- Report available storage and a labelled input-PCM equivalent duration. Do not
  treat compression as a fixed ratio or imply a guaranteed recording duration.
- Offer an explicit short input-test step separately. Inspection must not open
  capture streams, create a session, or claim to prove device availability.

Acceptance: a setup with an absent microphone, invalid channel selection, and
unusable output path reports each problem without starting capture. Structured
and readable output agree. Device changes after inspection remain possible and
are described as such.

Decided: absent selected devices are warnings; invalid configuration, channel
selections, and unusable output paths are failures. No required/optional source
schema was added.

## 2. Session quality report

Implemented: `recs session quality PATH`, with text/JSON metadata reports and
optional bounded audio analysis. Reports one document, not its continuation
chain. Native frame evidence is retained without cross-device alignment or
invented placement for unmapped audio. Read-only 48,000-frame blocks analyze up
to 60 seconds per fragment by default; per-channel run lists default to 100
entries, with explicit unexamined-frame and omitted-run counts.

Question answered: “Which parts of this recording should I inspect?”

Existing foundation: session summaries, journal explanations, media verification,
and recorded gaps/overflow evidence. Add a time-oriented report that connects
these observations to the affected tracks and intervals.

First version:

- Summarize captured duration, silence-suppressed intervals, dropped frames,
  disconnected periods, unfinished files, and unresolved placement per source.
- Add optional bounded audio analysis for sample peaks, near-full-scale runs,
  and per-channel signal levels. Keep metadata inspection fast by default.
- Produce readable and machine-readable results with source positions, units,
  analysis settings, and references to the evidence behind each finding.
- Separate measured facts from suspicions. Near-full-scale samples do not prove
  clipping, low levels do not prove a bad microphone, and intentional suppressed
  silence is not lost capture.

Acceptance: fixtures containing known dropouts, intentional silence, a quiet
channel, and near-full-scale passages yield correctly located, distinct findings.
Analysis does not alter media or invent positions for unresolved historical audio.

Decided: configurable −0.1 dBFS near-full-scale advisories, measured peak/RMS
levels without automatic quietness verdicts, and no opaque quality score.
Intentional suppression/discard is informational; known loss and incomplete
evidence warn. Read/analysis errors fail the command; warnings/advisories do not.

## 3. Searchable session library

Implemented: `recs sessions ROOT` accepts source/track, marker, media, capture-date,
incomplete-state, and warning filters. Filters combine with AND; text matching is
case-insensitive substring matching. Dates use the recorded calendar date with
inclusive `--since` and exclusive `--before`. Results include match explanations,
use path order, and default to a configurable 100-result limit. Truncation and
unreadable documents are reported without suppressing healthy matches. No media
decoding, persistent index, database, or new tagging schema was added.

Question answered: “Where is the take with that device, marker, or problem?”

Existing foundation: directory-based session listing and per-session summaries.
Extend the existing browsing interface with filters rather than introduce a
separate catalog service.

First version:

- Filter by capture date range, source/track name, marker text, media kind,
  incomplete state, and recorded warnings.
- Return the matching session plus a short explanation of why it matched.
- Support deterministic ordering and bounded result counts in readable and
  structured output.
- Read session metadata and journals, not audio payloads. Continue reporting
  unreadable entries without hiding otherwise healthy sessions.

Acceptance: combined filters return only matching sessions; moving a recording
root does not invalidate results. One malformed session does not abort a search.

First-version limit: no database, persistent index, transcription, or new tagging
schema. Measure ordinary filesystem search before considering a cache.

## 4. Marker-based extraction

Implemented: `recs session markers` lists numbered evidence, and `recs session
extract` previews a one-clock range by default. `--destination` invokes the
existing renderer, writes float32 WAV tracks and a resolved edit, and retains
marker provenance in the new session journal. Numbered selections disambiguate
labels. Lead/tail seconds round once to frames and trim to the common selected
extent. Unpositioned marks, mixed clocks, open recordings, and unresolved audio
are refused. Original sessions are never modified.

Question answered: “Can I save the passage I marked without writing frame ranges?”

Existing foundation: live marks/key events and non-destructive clip/edit commands.
The addition is resolving selected markers into an ordinary edit definition.

First version:

- List markers with their labels and available timing evidence.
- Select a passage between two explicitly chosen markers, or around one marker
  with requested lead-in and tail durations.
- Preview the resolved source tracks and half-open frame ranges before rendering.
- Save the resolved edit and provenance, then use the existing renderer to write
  a new session. Leave the original recording and markers unchanged.

Acceptance: repeated labels require an unambiguous selection; boundaries and
lead-in/tail trimming are exact once mapped to a source clock. Missing or
insufficient clock evidence produces an explicit limitation, not guessed alignment.

First-version limit: one source clock at a time. Wall-clock labels and host
timestamps must not be treated as proof of sample alignment across devices.

Approved and implemented prerequisite: explicit `mark` records retain each active
source's latest processed boundary, capture clock, sample rate, and observed
timestamp. Backlog may make that boundary older than the button press; it is not
a wall-clock interpolation. Restarted or paused sources contribute no stale
positions. Older markers remain unpositioned unless explicitly aligned.

## 5. Assisted recovery into a new session

Implemented: `recs session recover` previews a stopped version 4 segment and
creates a separate copy only with `--destination`. Completed media is verified
through the existing finalizer/checker; readable unfinished audio is preserved
as unplaced assets, without stream ports or invented ranges. Missing/invalid
files and unsupported unfinished event files are reported as omissions.
Original journal bytes and a detailed report are included as sealed assets.
Staged copies are verified before publication; failed partial work is retained
and reported. No uFor schema change was needed.

Question answered: “What usable material can I recover from an interrupted run?”

Existing foundation: unfinished-session reports, journal parsing, finalization,
and explicit historical conversion. Add a reviewed recovery workflow, not an
automatic repair during recorder startup.

First version:

- Inspect available journal entries and decodable media, then present a recovery
  plan distinguishing verified facts, missing files, and uncertain timing.
- On explicit request, create a separate recovered session using only supported,
  verifiable evidence. Preserve the original files and journal bytes.
- Record the recovery decisions and omitted material in the new session's
  provenance. Reuse current finalization and verification code.
- Refuse to invent interior silence positions or claim unresolved assets are
  aligned. Codec-specific salvage is outside the first version.

Acceptance: interrupted journals, missing media, and readable files lacking a
completion entry produce deterministic plans. A failed recovery leaves originals
unchanged and cannot expose an incomplete destination as a completed session.

Decided: the new session is sealed when recovery completes; that is not a claim
that the original capture was complete. Omissions and uncertain timing remain
explicit in the report and original evidence. Unplaced audio is not exposed as
an aligned track. The generated header/footer describe the recovery operation.

## 6. Resumable verified export

Implemented: `recs session export --resume STAGING` verifies the same sealed
source documents and all completed staged assets before reuse, restarts partial
files, and retains atomic progress reports on interruption. Copied, reused and
verified, remaining, and failed files are reported separately. Publication follows
full staged-asset verification; changed documents, corrupted completed assets,
unsafe paths, and existing destinations are refused. Originals are never removed.

Question answered: “Can I finish this large archive copy after the disk disconnects?”

Existing foundation: export already follows continuation chains, verifies assets,
and publishes a completed destination only after success. The new capability is
resuming recognized partial work, not merely adding checksums.

First version:

- Preserve identifiable staging progress on interruption and report its location.
- On an explicit resume request, verify completed staged assets against the same
  sealed source document before reusing them. Restart incomplete files.
- Report copied, verified, remaining, and failed items separately.
- Publish the final destination only after full verification. Never overwrite an
  unrelated directory or delete the source recording as part of export.

Acceptance: interruption followed by resume produces the same portable result as
an uninterrupted export. A changed source document, corrupted staged asset, or
unrelated destination is detected rather than trusted.

First-version limit: local filesystem destinations, whole-file restart, one
export worker. No remote storage, background service, or automatic retention policy.

## 7. Aligned track handoff

Implemented: `recs session handoff` previews a source-frame interval and writes
32-bit float WAV tracks plus a documented JSON sidecar with `--destination`.
The shared editor preserves offsets, channels, and silent gaps; source identities,
gap reasons, and positioned markers remain in the sidecar and edit provenance.
The first version accepts one sealed, unlinked segment on one integer-rate clock.
Publication waits for all audio and sidecar writes to finish.

Question answered: “Can I import these tracks into another editor at the right positions?”

Existing foundation: exact source spans, explicit gaps, channel maps, and offline
rendering. Add a focused export recipe for an editor-friendly track bundle.

First version:

- Produce one file per selected track over an explicit shared interval, with
  consistent origin, channel order, encoding, and deterministic filenames.
- Represent known timeline gaps as silence while retaining a companion report
  distinguishing suppressed silence from missing capture.
- Include track names, source identities, origin positions, and applicable
  markers in a simple documented sidecar. Reuse ordinary edit/session provenance.
- Require compatible clocks and rates. Do not add implicit resampling, drift
  correction, or cross-device synchronization under the name of export.

Acceptance: tracks from one recorded device import with their original relative
offsets, gaps, and duration. Unresolved placement and unsupported clock/rate
combinations are rejected before output generation.

Decided: 32-bit float WAV plus a documented JSON sidecar, matching the existing
renderer and preserving headroom without promising DAW-specific project formats.

## 8. Edit resource planning

Question answered: “Does this edit fit, and where will its temporary audio go?”

Existing foundation: bounded audio buffers, temporary float32 storage, and
composition resource summaries. Extend these into a planning step before full
source materialization, plus explicit scratch-location control.

First version:

- Show output frame counts, source/intermediate storage estimates, destination
  storage estimates, and the distinction between scratch disk and working RAM.
- Let the user select a scratch directory for the invocation, without changing
  capture output or saved recording settings.
- Identify source metadata that requires inspection; report unknown estimates
  honestly rather than decoding an entire recording merely to preview it.
- Check space before expensive work and preserve existing I/O failure handling:
  a successful check cannot reserve capacity against other processes.

Acceptance: planning a long sparse edit does not decode or allocate its full
timeline. The chosen scratch location is used consistently; storage failures
leave no apparently complete output session. Estimates state their assumptions
about sparse files, compressed outputs, and live intermediate lifetimes.

## Implementation discipline

Select and approve one feature at a time. Extend existing commands and processing
paths instead of adding aliases, duplicate renderers, or parallel session formats.
Proposed labels here are not commitments to new CLI command names.

Tests should exercise user-visible results with deterministic local fixtures.
Audio regressions use 48 kHz WAV files lasting at least one second. Device tests
remain explicitly requested checks, not ordinary unit tests or background probes.
No proposal authorizes deleting originals, uploading recordings, adding a database,
or implementing another project's responsibilities.

## Additional work beyond the prompt

None. This document proposes features only; it implements none of them.
