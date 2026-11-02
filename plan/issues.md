# Codebase review and cleanup issues

Reviewed 2026-11-02. recs revision `6994aae`; sibling reccy revision `9b5f1d4`.

The original review was static, not hardware qualification or proof that every
execution path is safe. The package inventory and cross-cutting searches covered capture,
audio, configuration, daemon/API, UI, MIDI/OSC, recording persistence/recovery,
and offline editing. Detailed inspection concentrated on ownership, blocking,
persistence, and public error boundaries. During that review no application or tests were run and
no implementation was changed. Proposed regressions below are acceptance criteria.
Sibling reccy is not necessarily the revision installed by recs's lockfile.

Priority: P1 can lose material, hang shutdown, or corrupt results; P2 affects
reliability, API usability, or substantial efficiency; P3 is maintainability.
“Confirmed” means visible in the current source, not reproduced on hardware.

## Implementation status

Issues 1–16 have been implemented with the approved policies. Additional work
beyond the prompt: None. RPC callers in showCo, streamO, lyte, and baccy are part
of the approved coordinated contract change. The original findings below remain
as the review record, rather than describing the updated implementation.

| Issues | Resolution |
| --- | --- |
| 1 | RMS no longer mutates cached samples; signed 48 kHz WAV regression. |
| 2 | Cancellable offline backpressure, read-error propagation, stop checks, duration default 100 seconds. The byte limit remains independent. |
| 3 | Coalesced GUI writer; bounded terminate/kill/reap; no buffered close behind a blocked writer. |
| 4 | Complete-message receiver isolated from the capture consumer; bounded handoff and terminal errors. |
| 5 | Each MIDI poll drains only its initial packet budget. |
| 6 | Expected reccy/filesystem errors handled at CLI and control boundaries; snapshot failures logged independently. |
| 7 | Journal reads share a contextual error boundary; truncated final records warn and leave recordings open. |
| 8 | Bounded loss observations with an explicit unlocated coalescing marker. |
| 9 | Calibration deadlines 20/21 seconds, other commands 5/6; queued cancellation and explicit unknown outcomes for started mutations. |
| 10 | Shared structured errors, typed exceptions, correlation IDs, conflict errors, coordinated wire version change and error-handling example. |
| 11 | Waveform worker retained and joined; restart rejected while the prior worker survives. |
| 12 | Persistent ordered offset manifest, explicit resume, filesystem preflight, interrupted rename/replacement regressions. |
| 13 | Preroll and recovery deques avoid shifting retained histories. |
| 14 | Renderer bus/route lookups cached; constant gains use a broadcast scalar owner. Small-channel Python reductions retained after measurement. |
| 15 | Ownership-aware retained-audio categories, pending-loss/control/transport bounds, independent input queue budget. No process RSS cutoff. |
| 16 | `settings.save(sync=False)` for atomic health snapshots, published through a bounded optional worker. Default user-settings durability unchanged. |

### Measured efficiency

Local macOS microbenchmarks (not Pi qualification): draining 10,000 retained
entries took 6.06 ms with list head removal and 0.33 ms with deque. A 48,000-frame
constant gain owner fell from 192,112 bytes to 100 bytes. Python mean reductions
on one/two channels took 0.40/0.44 microseconds versus 1.13/1.14 for NumPy;
Python extrema were also marginally faster there, so those common per-track
reductions retain their existing integer widening and NaN behavior.

A synthetic 28-channel float32 workload retaining 200 blocks of 4,800 frames
through two-channel views exposed only 7.68 MB of samples while retaining
107.55 MB of backing allocations; observed process peak RSS was 151.49 MB.
This demonstrates why visible slice bytes and input queue limits are not process
memory limits. The workload wrote a one-second 48 kHz WAV; it did not capture
hardware or simulate venue storage latency.

## P1: correctness and liveness

### 1. RMS mutates cached audio samples (confirmed)

`recs/audio/block.py`, `Block.asfloat` and `Block.rms`: for integer input,
`asfloat` caches a converted floating array. `rms` obtains that array and squares
it in place because it is different from `self.block`. Subsequent reads of
`block.asfloat` therefore return squared samples. The result depends on whether
RMS was inspected first. Original integer samples survive, but the public cached
conversion is corrupted.

Fix: compute squared magnitudes in a separate temporary/reduction without
mutating either representation. Regression: signed 48 kHz integer WAV, at least
one second; compare conversion before/after RMS and alternate property order.

### 2. Offline file ingestion can drop audio under ordinary backlog (confirmed path)

`recs/cfg/file_source.py`, `FileSource.input_stream`, reads 4096-frame blocks as
fast as storage allows and feeds the same dropping `InputBuffer.put` used for
live capture (`recs/runtime/input_buffer.py`). There is no producer backpressure.
A long file can outrun silence analysis/encoding and exhaust the ten-second or
memory limit. Dropping is appropriate as an explicit last resort for live input,
but unnecessary and destructive for a seekable offline file.

Fix: cancellable backpressure for file producers, or consumer-driven file reads;
keep the hardware callback nonblocking. Also check the stop flag between reads:
the current file loop continues to EOF after a stop request. Regression: long
file, deliberately slow consumer, small capacity, exact retained sample counts;
stop must terminate reading promptly. Surface read-thread errors to the owner,
rather than relying solely on `finally: result.stop()`.

### 3. GUI pipe writes and process shutdown have no complete bound (confirmed)

`recs/ui/gui_process.py`, `update`, `stop`, `join`: synchronous stdin writes and
flushes can block if the child stops reading. Closing the buffered stream can
also wait behind an in-progress write. `join(None)` waits indefinitely; after a
timeout the code terminates and then calls unbounded `wait()` without a kill
fallback. A wedged optional GUI can therefore delay cleanup indefinitely.

Fix: bounded/coalesced optional UI publication and bounded terminate/kill/reap.
Reuse `reccy.runtime.process.terminate` for the subprocess escalation where its
contract fits; handle its final timeout explicitly. This helper alone does not
solve blocked pipe publication. Regression: child stops reading and ignores
termination; recording shutdown must finish within the declared deadline.

### 4. Partial control messages can block the capture consumer (confirmed path)

`recs/runtime/source_transport.py`, `SourceControlHandler.receive`: `poll()` only
establishes that bytes are readable; `recv()` waits for a complete multiprocessing
message. A parent stalled halfway through a large configuration send leaves the
child's consumer waiting while capture fills its bounded queue. The parent has
an isolated sender, but the child directly receives on its processing path.

Fix: isolate complete-message reception from audio processing with a bounded
handoff and an explicit terminal error. Regression: send only a message header
and part of the payload, then request stop and keep supplying audio. This is a
liveness hazard, not a claim that normal messages routinely fragment this way.

### 5. MIDI draining has no per-poll work bound (confirmed)

`recs/midi/recorder.py`, `CallbackPort.iter_pending`: drains until `Empty`, while
a callback may keep enqueueing. Queue capacity bounds pending memory but does
not bound the returned list or time spent draining a continuously replenished
queue. This can monopolize the owner's polling cycle.

Fix: snapshot/bounded packet budget per poll and retain the remainder for the
next cycle. Preserve capture timestamps and existing overflow accounting.
Regression: producer replenishes while draining; each poll must return within
a bounded packet count and permit other sources/control work to progress.

## P2: errors, persistence, and concurrency

### 6. CLI error boundaries do not cover current dependency exceptions (confirmed)

`recs/__main__.py:run` catches `ValidationError` and `RecsError`, but not
`reccy.errors.ReccyError` or general filesystem failures. Direct saves in
`recs/daemon/instances.py` and `recs/daemon/gui_ipc.py` can raise `ReccyError`;
service-controller failures can also propagate through delegates. Some settings
callers translate errors to `RecsError`, others expose dependency types.

Fix: define expected user-facing failures at CLI/RPC boundaries, preserve causes
for logs, and retain tracebacks for programming defects. Do not add blanket
exception swallowing to every helper. Test failed status publication, instance
publication, service operations, and unwritable destinations through public
entry points. Ensure failure reporting does not replace the original failure.

### 7. Saved-index journal reads escape the reader's error wrapper (confirmed)

`recs/recording/read.py:read_recording`: index parsing is inside a try/except,
but the subsequent `session_record.read_entries(original)` is outside it.
A journal becoming unreadable/disappearing between `is_file()` and `open()`
raises raw `OSError`. Identical underlying failures therefore have different
public types depending on whether the caller opened a journal or an index.

Fix: put all required reading under the same contextual error boundary. Test
permission failure and removal after discovery. Decide and document truncated
journal policy: this path rejects errors while raw journal preparation has
special handling for a truncated final record. Avoid silently discarding loss
evidence when deciding recovery policy.

### 8. Unknown-loss evidence has an unbounded side queue (confirmed)

`recs/runtime/input_buffer.py:put` appends each overflow observation to
`unknown_losses` before checking memory/capacity; `take_unknown_losses` clears it
on consumption. Under a prolonged blocked consumer and repeated backend
overflows, the audio budget does not bound this list.

Fix: bound/aggregate observations while retaining an honest indication of
unlocated or coalesced unknown loss. Do not invent missing frame counts or drop
the fact of loss. Regression: indefinitely repeated overflow reports with a
stalled consumer and a fixed audio budget.

### 9. Control deadlines and cancellation need one explicit contract (confirmed)

`recs/daemon/external_ipc.py:ControlRequest.wait/rpc_response` uses five seconds;
`reccy/protocol/rpc.py:Client` defaults to one second. `doc/recs_protocol.md`
already documents calibration potentially taking fifteen seconds. A timeout can
occur while a mutation continues. Cancellation is checked before enqueueing,
but later client disconnection does not directly cancel queued work.

Fix: align operation deadlines or return an accepted operation with observable
completion for genuinely long operations. Distinguish not-started cancellation
from outcome-unknown timeout. Never blindly retry a mutation after timeout.
Regression: timeout before start, during execution, and immediately before
response publication. Verify effects occur at most as specified.

### 10. Error results lose machine-readable meaning (confirmed API limitation)

The wire `ipc.Error` carries a message; reccy's `Client.call` converts server
errors to `ConnectionError`, the same family as transport failure. recs also
returns a structured track-name conflict as an ordinary result. Clients must
know command-specific shapes and/or parse human text to distinguish rejection,
conflict, busy, transport failure, and unknown mutation outcome.

Fix in reccy: a small structured RPC error model plus typed client exceptions,
with stable code and execution/outcome information where actually known.
Preserve transport exceptions separately. Map expected domain failures at a
single server boundary; log unexpected exceptions with a correlation identifier
and return a safe internal-error result. Adopt this across projects together,
not through independent recs wrappers or a generic retry decorator.

### 11. Waveform worker lifetime is not owned across restart (risk)

`recs/daemon/external_ipc.py:start/on_stopping` starts a daemon thread without
storing/joining it and reuses stop/available events. A rapid stop/start can clear
the stop flag before the old worker observes it, leaving multiple publishers.
Determine whether reusing an ExternalServer instance is supported; if it is,
retain and join the worker before restart. Otherwise enforce single-use lifecycle.
Regression: block publication while stopping and restart the same instance.

### 12. Offset staging protects bytes but is not a recoverable transaction (confirmed limitation)

`recs/recording/offset.py:offset_sessions` stages directories and replacement
metadata, then moves them into place sequentially. Failure preserves files and
reports the staging directory, which is useful, but there is no persisted
source/destination operation manifest or resume/rollback command. Partial
publication leaves a mixture of old/new locations and continuation references.

Fix: save a minimal operation manifest before the first move and define recovery
for every stage. Do not promise all-or-nothing semantics for a multi-directory
rename. Inject failures at each rename/replace and verify discoverability and
recovery without guessing numeric staging names. Check filesystem boundaries
before mutating, because a recursive root may contain mounted volumes.

## P2/P3: audio efficiency and memory ownership

### 13. Preroll/recovery head removal repeatedly shifts Python lists (confirmed cost)

`recs/audio/block.py:Blocks.clip` uses `pop(0)`; `recs/audio/channel_writer.py`
removes recovery blocks from the head similarly. Fixed detector windows bound
ordinary block sizes, but large configured histories multiply repeated list
shifts across tracks. Consider deque or a head cursor only after measuring the
configured workloads. Preserve exact partial-block clipping and sample ownership.

### 14. Small-array reductions and graph lookup repeat avoidable work (confirmed)

`Block.volume` uses Python `sum` over a NumPy array. SourceRecorder's uncertain
window check uses Python min/max over channel extrema. Use array reductions
where benchmarks show benefit; small channel counts can make overhead dominant.
Keep integer widening and NaN policy explicit.

`recs/edit/render.py` rebuilds the bus lookup and scans every route for every bus
on each rendered block. Precompute stable bus/route adjacency when constructing
the renderer. Constant gains also merit scalar fast paths rather than full gain
arrays, provided automation boundaries retain sample-exact semantics. Compare
peak memory and throughput as well as numerical output; do not replace NumPy
operations with per-sample Python loops.

### 15. Queue memory accounting is not a total capture memory limit (design limitation)

`InputBuffer` accounts backing NumPy owners and entry/view estimates. Consumer
windows, retained track preroll, pending quiet, replay history, forwarding, and
transport event history are additional allocations. Selected/overlapping tracks
can retain multiple arrays. Report these budgets separately and measure peak
RSS with realistic channel layouts; do not describe the queue ceiling as a
process memory guarantee. Track slices may keep larger owners alive after a
partial trim. Prefer ownership-aware measurement before adding copies.

### 16. Status publication synchronizes disk on the parent path (confirmed behavior)

`recs/daemon/gui_ipc.py:_write_status` now uses `settings.save`. The save path
synchronizes writes; status updates occur every second. This is a change from
previous `sync=False`, and slow storage can stall the parent even though audio
capture runs in children. Measure worst-case latency and whether it backs up
source event transport. Decide explicitly whether replaceable health snapshots
need the same durability as user settings; if not, reccy should expose that
policy through its save API rather than callers bypassing it inconsistently.

## API clarity, examples, and reccy reuse

The API is local newline-delimited RPC, not REST. Command names are generally
verb-based and the protocol document describes request/result shapes, but
command knowledge is repeated in `gui_protocol.py`, `external_ipc.response`,
`control_cli.py`, and the recorder dispatch modules. Mutation results mix `ok`,
structured state, and conflict objects. Review each command's declared response
and generate/validate dispatch coverage from a single command specification
before contemplating mass renaming. Distinguish recording pause, playback pause,
source identity, track label, capture clock, and session in every public example.

`doc/recs_protocol.md` explains errors and deadlines, but needs a complete
copyable Python example that handles remote rejection, connection failure,
timeout with uncertain mutation outcome, malformed responses, and event-stream
termination. Include a read-only example and a mutation/reconciliation example.
A success-path call and a catch-all print are not sufficient. The current client
cannot classify all those cases reliably until issue 10 is resolved. Test the
examples against an in-process fake server, without recording devices.

REST-like APIs do **not** all use the same error process. HTTP APIs can use
[RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html), while
[gRPC uses status codes and optional details](https://grpc.io/docs/guides/error/).
These are evidence for a shared conceptual classification, not a reason to put
HTTP status codes into local RPC or assume every provider supports Problem
Details. A reccy facility should separate domain errors, transport errors, and
adapter-specific serialization. Automatic mutation retries require explicit
idempotency semantics and must not be the default.

Concrete reuse candidates:

- `GuiProcess.join`: use reccy's bounded process termination (issue 3).
- `recs/daemon/controllers.py`: already delegates to reccy's service controller;
  investigate eliminating the wrapper only if callers can use its generic
  status model without casts and duplicated result construction.
- Settings loading in `cfg/mic_mute.py`, `cfg/projects.py`, and `cfg/settings.py`:
  compare with current `reccy.configuration.settings.load/read`. Preserve each
  caller's missing-file and malformed-file policies. The sibling load API has
  changed; do not mechanically substitute it based on an older signature.
- Atomic single-file publication: use `reccy.runtime.files.atomic_output` where
  semantics match. It syncs file contents when requested, not the parent
  directory. It is not a replacement for offset's multi-file transaction.
- Pull up the queued request/deadline state machine only alongside the structured
  error contract, if another project needs owner-thread execution. Keep recorder
  command semantics in recs.
- A bounded optional latest-value publisher with explicit close/failure reporting
  could serve GUI/status consumers in several projects. Do not unify it with
  durable capture-event delivery: coalescing rules differ fundamentally.

## Module responsibility and review coverage

`runtime/recorder.py` (1,199 lines) is the strongest decomposition candidate:
application lifecycle, session transitions, external commands, device callbacks,
and disk recovery share one owner. Extract cohesive operations with explicit
ownership/state only when fixing a concrete issue; avoid introducing more
forwarding wrappers. `source_recorder.py` combines control application, audio
processing, and lifecycle. Preserve one clear owner for each writer when splitting.
`gui_protocol.py` combines request/response schemas and command inventory; a
canonical command registry could reduce duplication with dispatch and CLI.
`edit/commands.py` deserves a separate pass over command expansion versus source
resolution; retain a single renderer and canonical edit schema.

Small modules are not automatically problems: `runtime/device_poller.py` adapts
the executable command for dvice, and `daemon/spec.py` supplies the service spec.
Their purpose is clear. `base/prefix_dict.py` is generic but too small to justify
promotion to reccy without another consumer. Audio formats/schema belong in
uFor, device supervision in dvice, and signal processing in recs; reccy should
not become a general dumping ground.

Additional edge-case review targets, not established bugs: malformed OSC bundles
and nesting depth; MIDI disconnect during file rotation; interrupted export
publication; cleanup errors masking encoding failures; event subscriber fairness;
NaN/Infinity input classification; disk unmount during journal closure; repeated
source restart resetting diagnostic/drain counters. Existing queue bounds,
status-aware capture windows, and explicit unknown-loss markers are useful
protections and should remain covered when fixing the findings above.

## Suggested implementation order

1. RMS ownership, offline backpressure/stop, bounded GUI shutdown, partial control
   reception, and bounded MIDI draining.
2. Normalize error boundaries and add failure-injection regressions; address
   bounded loss observations and waveform restart ownership.
3. Agree the reccy RPC error/deadline contract; update protocol examples and
   command/result coverage together.
4. Offset recovery manifest, then measured audio/renderer optimizations.
5. Decompose modules only where the preceding fixes establish a clear seam.

Hardware throughput and four-hour show qualification remain separate work.
No performance improvement or absence of races is established by this static review.

## Additional work beyond the prompt

None. Issues 1–16 are implemented; the remaining review suggestions are not part
of this change.

## Verification of the fixes

- recs: 1,235 tests passed against the updated locked reccy revision; Ruff
  B/E/F/I, formatting, type checking, pyupgrade, and diff checks passed.
- reccy: 578 passed, one skipped; formatting, Ruff, and type checks passed.
- showCo: 946 passed and 84 subtests passed; type check passed.
- streamO: 395 passed; type check passed.
- lyte: 568 passed, one skipped, and five subtests passed. The modified panel
  passes type checking; the full package has an unrelated existing type error
  at `lyte/rendering.py:121` involving `Composition`'s argument type.
- baccy: 221 tests passed in an isolated copy of committed code plus these RPC
  changes. Its existing uncommitted `discovery.py` uses exception syntax that
  its configured Python 3.13 cannot parse; that user change was preserved.
  The modified service module passes type checking.

No live recording, GUI application, service deployment, audio device, or
four-hour venue qualification was run. The tests use fixtures and simulated
failures. The remaining audit suggestions after issue 16 are unchanged in scope.
