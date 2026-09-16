# Repository issues

Reviewed 16 September 2026 against recs commit `351fb22`. This is a source
review, not a claim of exhaustive coverage or hardware verification. No application
or test suite was run for this documentation change. Findings below distinguish
source-confirmed behavior, conditional risks, and maintainability judgments.
Suggested acceptance checks are work for the eventual fixes.

P1 means potential loss of recording evidence, hangs, or incorrect operational
state. P2 means functional defects, user traps, or significant scaling limits.
P3 means documentation, naming, or maintainability work. These priorities do not
authorize implementation or a broad refactor.

## Lifecycle and correctness

### 1. P1: shutdown waits before draining the child's output pipe

Evidence: [SourceProcess.join](../recs/ui/source_process.py) waits for the
process, terminates it after the timeout, and only then reads pending updates.
[SourceUpdateTransport.finish](../recs/ui/source_recorder.py) waits indefinitely
for its sender to become idle; that sender uses blocking `Connection.send`.

Conditional failure: if final updates fill the pipe, the child cannot finish
until the parent reads, while the parent waits for the child to finish. A normal
stop can become forced termination, losing final file/timeline evidence.
Terminating during a message write also needs scrutiny: `poll()` does not prove
an entire serialized message is available for the following `recv()`.

Drain while waiting for exit, with an explicit shutdown deadline. Acceptance
needs a real subprocess and final messages larger than the pipe capacity,
checking both device-process retirement and preservation of final updates.

### 2. P1: failed update sends never release the finish waiter

Evidence: [SourceUpdateTransport](../recs/ui/source_recorder.py) clears `idle`
when publishing. Its send-error branch returns without setting `idle` or
recording a terminal transport state. `finish()` still calls `idle.wait()`.

Source-confirmed wait path: a broken update connection after publication can
leave shutdown waiting forever unless the parent forcibly terminates the child.
Completion and transport failure need explicit wakeup semantics. Test a broken
connection with a pending update and require bounded completion.

### 3. P1: playback resumes recording even when it was already paused

Evidence: [PlaybackControl.play, stop, and _finished](../recs/ui/playback_control.py)
discard the pause callback's result and unconditionally resume recording on
completion or stop. [pause_recording](../recs/ui/recording_commands.py) now
returns `was_paused`, but playback does not consume it.

A manual or disk-space pause followed by playback can therefore end with capture
unexpectedly enabled. Track whether playback acquired the pause, and define how
a new pause during playback affects restoration. Cover pre-paused recording,
natural end, failure, explicit stop, and session changes.

### 4. P1: playback failure resumes capture before closing playback output

Evidence: [PlaybackRunner._run](../recs/audio/playback.py) invokes `failed()`
inside its processing exception handler, before `stream.close()` in `finally`.
The [failure callback](../recs/ui/playback_control.py) clears the runner and
resumes capture immediately.

This creates a device-ownership race on systems that cannot open capture while
playback still owns the device. Those callbacks also mutate recording/session
state from the playback worker thread. Deliver a terminal result after output
closure, and establish one thread that owns controller transitions. Check the
ordering with fake output streams before hardware verification.

### 5. P2: playback preparation errors can leave recording paused

Evidence: [PlaybackControl.play](../recs/ui/playback_control.py) pauses recording
before constructing `PlaybackTimeline`; that constructor can reject a fractional
audio rate in [audio/playback.py](../recs/audio/playback.py).

If timeline preparation rejects a recording, no runner owns the pause and no
rollback restores the prior state. Prepare before pausing, or restore the acquired
pause on failure. Test an unsupported audio rate and verify recording
state is unchanged when playback never starts.

### 6. P1: collision handling can loop forever for a filename with a suffix

Evidence: [FileOpener.create and open](../recs/audio/file_opener.py) append the
collision counter to `path.name`, then replace the suffix using `with_suffix()`.
For an existing `take.wav`, retries `take.wav_1`, `take.wav_2`, etc. all become
`take.wav` again for WAV output.

This is a source-confirmed edge case in the public helper; whether normal
recording paths reach it depends on the supplied basename. Put the counter
before the extension or normalize the basename once. Check an existing path
with an extension as well as the ordinary extensionless path.

### 7. P2: profile reload reports success without updating live children

Evidence: [reload_profiles](../recs/ui/recording_commands.py) invalidates the
parent's cache and assigns `source.cfg`. It neither validates the replacement
file immediately nor calls [SourceProcess.set_cfg](../recs/ui/source_process.py),
which sends the resolved configuration to the child.

Running capture can continue with old settings after a successful response;
malformed replacement profiles can fail only later. Define reload as validated
and applied, or explicitly pending restart. Test both a changed valid profile
and a malformed one while a source is active.

## CLI and user traps

### 8. P2: watch help performs instance discovery before parsing help

Evidence: [watch.main](../recs/daemon/watch.py) calls `instances.resolve()` before
`tyro.cli()`. [Discovery](../recs/daemon/instances.py) probes descriptors serially
with one-second RPC timeouts. An unavailable explicit instance can reject
`recs watch --instance PID --help`; default help can wait on stale descriptors.

Parse help before resolving a live target. Acceptance: help succeeds without
RPC calls, including when an instance selector is supplied.

### 9. P2: several command groups have no usable help path

Evidence: [session_browser.main](../recs/ui/session_browser.py) treats its first
argument as a path, so `recs sessions --help` scans a path called `--help` and
returns success. The `session` fallback in [the dispatcher](../recs/__main__.py)
also lets a misspelled subcommand become a directory scan. `record --help`
exits with a usage error in [session_record_check](../recs/ui/session_record_check.py);
`edit --help` enters recipe resolution in [edit/cli.py](../recs/edit/cli.py).

Provide explicit group help and distinguish unknown commands from paths.
Keep internal helpers such as `query-devices-stream` out of blanket help
enumeration: the dispatcher currently executes them without checking `--help`.

### 10. P2: help regression coverage omits the public subcommands

Evidence: [test_help](../test/cfg/test_cli.py) calls `cli_help('recs', run)`
without subcommands. Its [snapshot](../test/cfg/test_cli/test_help.txt) describes
recording options but does not discover the daemon, control, profile, session,
watch, or edit interfaces dispatched by `__main__.py`.

The shared reccy facility was adopted only for top-level help. Add explicit
public command coverage and suitable nested-group fixtures after their help
paths are safe. Keep parsing and behavior tests; they are not redundant with
snapshots.

### 11. P2: one malformed recording blocks playback selection for the library

Evidence: [PlaybackControl._sessions](../recs/ui/playback_control.py) parses every
discovered `recording.toml` in a list comprehension. Any `RecsError` aborts the
entire selection, including requests for an unrelated valid session. By contrast,
[session_browser.summarize](../recs/ui/session_browser.py) silently omits documents
it cannot read.

Choose a consistent policy that reports bad entries while keeping healthy
recordings accessible. Test a library containing both valid and malformed scores.

### 12. P3: similar CLI words name different operations

Evidence: [the dispatcher](../recs/__main__.py) exposes `sessions`, `session`, and
`record`, while capture itself uses the bare command. In
[control_cli.py](../recs/daemon/control_cli.py), `pause` and `resume` concern
recording, but `stop` and `continue` concern playback. A saved setup `profile`
also differs from the per-device defaults loaded with `--profiles`.

These are user-facing naming traps. Document the distinctions in help first;
settle one vocabulary before any explicitly approved command rename. Do not
add more aliases as a substitute for deciding the intended interface.

## Performance and scaling

### 13. P2: edits allocate whole source and timeline arrays

Evidence: [Renderer](../recs/edit/render.py) materializes sources up front and
allocates arrays through the maximum output end for every track and bus.
Normalization and gain application can allocate further arrays. See also
[materialized.py](../recs/edit/materialized.py).

An hour of 48 kHz stereo float32 is about 1.29 GiB for just one array. Several
tracks, buses, and intermediates can exhaust memory even for sparse timelines.
Memory-error reporting does not provide a budget or bounded rendering. Decide
the supported edit size and block/cache strategy, then measure peak memory on
a representative long edit. A streaming redesign requires separate scope.

### 14. P2: gain automation evaluates Python code once per audio frame

Evidence: [gain_values](../recs/edit/automation.py) builds full position and gain
arrays, then calls the scalar uFor evaluator through a list comprehension for
every selected tick. At 48 kHz, one hour means 172.8 million calls per lane.

Preserve the specified interpolation while evaluating segments in vectorized
or bounded blocks. Compare output against the scalar reference and measure a
long lane; no performance benchmark was run during this review.

### 15. P2: playback rescans all fragments and reopens files per block

Evidence: [PlaybackTimeline.read](../recs/audio/playback.py) iterates the complete
fragment list and opens, seeks, reads, and closes each intersecting file on every
call. The runner normally requests 2,048 frames at a time.

Cost scales with total fragment count for each block, plus repeated decoder
setup for a file spanning many blocks. Index intervals and consider bounded
reader reuse with explicit closure. Benchmark fragmented recordings while
preserving gap behavior and random seeks.

## Structure, documentation, and unfinished decisions

### 16. P3: ui contains most of the capture and persistence subsystem

Evidence: `recs/ui/` has 34 tracked-source entries in this review, including
source processes, audio buffering, disk policy, session records, export,
recovery, and playback control. [AGENTS.md](../AGENTS.md) describes the directory
as orchestration and terminal status, which understates its actual ownership.

The count alone is not excessive; the mixed responsibilities make the name
misleading and changes hard to locate. Establish a package map by responsibility
before moving anything, and migrate only a coherent area when authorized.

### 17. P3: several modules and tests combine too many responsibilities

Measured source lengths at review time:

| File | Lines | Review concern |
| --- | ---: | --- |
| [source_recorder.py](../recs/ui/source_recorder.py) | 1,054 | transport, buffers, calibration, file events, control application, capture, and update merging |
| [recorder.py](../recs/ui/recorder.py) | 904 | application wiring, control flow, session transitions, status, and collaborator forwarding |
| [autocalibrate.py](../recs/edit/autocalibrate.py) | 889 | schema, preparation, statistics, interval detection, rendering, and output persistence |
| [cfg.py](../recs/cfg/cfg.py) | 856 | option sections, flat compatibility access, profiles, units, and derived runtime settings |
| [test_recorder.py](../test/ui/test_recorder.py) | 2,409 | shared fakes and many unrelated recorder behavior families |

These are maintenance judgments, not line-count rules. Extract along stable
responsibilities when changing those areas; do not split by arbitrary size.

### 18. P2: the plans disagree about what has been completed and authorized

Evidence: [sample-playback.md](sample-playback.md) still says waveform work is
postponed and a synth definition must be added. The corrected
[enge handover](enge.md) explicitly assigns synth consolidation and sampler
implementation to enge. The [master verification document](master/verification-procedures.md)
still lists preparation/action traces as open, while
[sample-format.md](sample-format.md) and [deferred-work.md](master/deferred-work.md)
mark that work complete. The [recs handover](../doc/handover.md) describes
same-rate automation acceptance as future work, although
[Renderer._automation](../recs/edit/render.py) already enforces it.

These contradictions have already caused an incorrect enge handover. Reconcile
status and authority, distinguish historical gates from current instructions,
and link to one current owner for each remaining task. General automation rate
conversion remains a separate design decision; its absence is not itself a bug.

### 19. P3: document titles and package metadata obscure authority

Evidence: `plan/master/verification-procedures.md` is 946 lines of roadmap,
architecture, history, and verification; `future-proposals.md` is 1,184 lines
and also contains implemented profiles. `plan/master/complete/README.md` says no
document is wholly complete. This makes finished work difficult to distinguish
from proposals. Several documents also retain superseded project capitalization.

[pyproject.toml](../pyproject.toml) declares version `0.12.5` under `[project]`
but keeps `0.12.0` under `[tool.poetry]`, despite building with Hatchling. The
duplicate metadata invites incorrect tooling or manual release edits.

Clarify the active document index and canonical packaging metadata. Use the
agreed names: lyte, streamO, recs, uFor, reccy, tuney, enge, showCo.

## Additional playback data-integrity finding

### 20. P1: playback discards multiple spans of the same asset

Evidence: [_fragments](../recs/audio/playback.py) deduplicates by
`fragment.variant_group or fragment.asset` using `setdefault`. Multiple fragments
without a variant group that reference different ranges of the same asset keep
only the first range. Such ranges represent legitimate separate timeline spans,
including silence-trimmed captures; asset identity does not identify an
alternative encoding of one interval.

The same preparation path ignores `unmapped_fragments`, making an unresolved
historical recording potentially sound like missing audio or silence instead of
reporting unsupported placement. Preserve every selected span, distinguish
encoding alternatives from timeline intervals, and reject unresolved placement
explicitly. Check repeated assets with different source offsets and timeline
positions, variant encodings, and an unresolved historical stream.

## Suggested order

Address shutdown/evidence preservation and pause ownership first, then filename
collisions, lost playback spans, and live profile reloads. Repair public help and extend its regression
coverage. Reconcile the plans before assigning more cross-project work. Measure
the edit/playback scaling limits before selecting architectural changes.

## Additional work beyond the prompt

None. This review records issues and proposed acceptance checks; it implements
no fixes and changes no production recordings.
