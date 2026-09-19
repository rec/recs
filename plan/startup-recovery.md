# Startup recovery worklist

## Goal

Report each unresolved recording once when recs first discovers it, report it
again only when its recovery-relevant evidence changes, and avoid recursively
scanning a recording volume at every capture startup.

This applies to the automatic startup diagnostic only. It does not alter
`recs session recover`, finalization, journal parsing, or the rule that an open
recording remains explicit evidence rather than a sealed asset.

## Current failure

`Recorder._start_record()` calls `report_unfinished_sessions()` for the whole
configured recovery root. That function recursively finds every
`session-record.jsonl`, regenerates `recs-recovery-report.toml`, and logs an
error for every unresolved session. Consequently an old interrupted session is
read, rewritten, and reported on every later startup, even when neither its
journal nor its media has changed.

## Design

Keep a small target-local recovery worklist under recs' existing state
directory, rather than on the recording volume. It is a cache of known
unresolved journals, not recovery evidence and not an authority on whether a
recording is sealed.

Each worklist entry records:

- the absolute journal path and the recovery root that discovered it;
- a journal identity and fingerprint, including device/inode where available,
  size, and modification time;
- the relative media paths used by the prior report and their existence/size/
  modification-time fingerprints;
- the canonical generated-report digest; and
- whether that exact report has already been announced.

At startup recs reads this local worklist. It inspects only its entries. A
journal is recomputed and its report is written and announced only when it is
new, its journal fingerprint changed, a tracked media fingerprint changed, the
generated sidecar is missing or differs from the stored digest, or its prior
inspection was interrupted. An entry whose journal has become sealed is removed
from the worklist. A missing journal is retained as a quiet unavailable entry,
so a temporarily unmounted volume does not turn into a new warning storm when
it returns.

The first use of a recovery root, or an explicitly requested rescan, performs
the current recursive discovery once. It adds unresolved journals to the
worklist and records that root's filesystem identity and discovery completion.
A later startup does not recurse through a root whose identity has already been
discovered. If the root resolves to a different filesystem, recs treats it as a
new root and performs one discovery scan. This preserves discovery for a newly
mounted recording disk without repeatedly traversing the same disk.

Every recs-created journal is registered in the worklist before its header is
opened. A clean finalization removes its entry only after the sealed
`recording.toml` is successfully written. A crash therefore leaves a known
candidate for the next start without requiring a volume scan.

Add an explicit `recs session recover-scan ROOT` command for the operator who
wants discovery on an already-indexed root. It performs the one-time discovery
pass, updates the worklist, and reports only new or changed unresolved sessions.
It does not modify journals, media, or sealed recording documents.

## Implementation steps

1. Add a versioned Pydantic recovery-worklist model and platform-aware state
   path beside the existing recs service state. Read and write it atomically.
   Treat a malformed or unavailable worklist as an empty cache, log one local
   warning, and perform discovery rather than losing recovery visibility.
2. Split `recovery_report.report_unfinished_sessions()` into pure inspection,
   report publication, candidate fingerprinting, and root discovery. Preserve
   the current `RecoveryReport` TOML format and its atomic sidecar writes.
3. Implement worklist refresh for known candidates. It must distinguish an
   unchanged report from changed journal or media evidence, suppress duplicate
   logging for unchanged reports, and remove only a generated sidecar whose
   stored digest proves recs owns it after a session becomes sealed.
4. Replace the unconditional startup `rglob` in `Recorder._start_record()` with
   a worklist refresh. Register the pending journal before `RecordingSession`
   opens it, and clear the entry after successful finalization. Cover normal
   stop, `new_session`, output-directory changes, and card replacement, because
   each can create a distinct journal.
5. Add `recs session recover-scan ROOT` as the explicit discovery path. It
   performs discovery, writes reports only for new or changed unresolved
   sessions, prints their paths, and leaves journals, media, and sealed
   recording documents unchanged. Document that it is the manual route for
   externally copied historical sessions added after a root's first scan.
6. Update the README and recovery documentation to say that startup checks the
   worklist, first encounters are discovered once per recording filesystem, and
   manual rescans find externally introduced history.

## Tests and acceptance

- A first discovery writes and logs one report per unresolved journal.
- A second startup with unchanged journal, media, and report performs no
  recursive root scan, rewrites no report, and emits no repeat recovery error.
- Changing an open journal, adding or removing a referenced media path, or
  deleting the generated report causes exactly that candidate to be inspected,
  republished, and announced once.
- A cleanly finalized session is removed from the worklist and its owned stale
  report is removed; a user-modified sidecar is preserved.
- A crash after journal registration and before finalization is reported on the
  next startup without a root scan.
- A newly mounted filesystem at the same configured root is discovered once;
  an explicit `recover-scan` discovers historical journals copied into an
  already-indexed root.
- Existing recovery, finalization, and session-browser tests continue to prove
  that incomplete evidence is never silently sealed or overwritten.

## Additional work beyond the prompt

Add `recs session recover-scan ROOT` as the deliberate discovery route for
historical sessions introduced after a root's initial scan. It is needed to
retain discoverability without restoring automatic volume-wide scans; it is a
proposal only until this plan is approved for implementation.
