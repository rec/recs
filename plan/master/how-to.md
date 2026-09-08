# How to build the common model

Part of the [master proposal](master.md). Stage 2 is complete. On 8 September
2026 the user requested a plan revision prioritizing tuning/scale and oscillator
extraction, richer envelopes/LFOs, and deferring further waveform generation.
The subsequent Ufor extraction is implemented; see [its handover](ufor.md).
The first envelope/LFO control profile is implemented in Ufor. The final
instrument root, slices, channel maps, source bindings, and SFZ conversion are
now implemented in Ufor. Preparation/action traces remain stage 3 work. Shared
performance events and typed scalar routes are implemented; see the [instrument contract](../../../ufor/doc/instrument-format.md).
Additional work beyond the prompt: None.

## Implementation status

Stages 1 and 2 are implemented in Recs. The supported
subset has pure common models, exact rational physical timebases, sealed assets, common event envelopes,
structured source and parameter references, and typed audio ports. Audio editing
now uses the common arrangement document, with file destinations separate from
public outputs. Existing rendered-audio regression behavior is retained.

Recording and sequence documents have a common parser, TOML serializer, and
generated JSON Schema through `document_schema()`. The explicit
`recs session migrate` converter prepares historical version 3 sessions. New
captures and successful audio edits finalize `recording.toml`; browsing,
checking, export, and session-source resolution consume it. See the
[implemented recording format](../../doc/recording-format.md)
for complete examples, defaults, verification, and conversion instructions.

The earlier checkpoint commits, each tested and pushed, are:

| Commit | Change |
| --- | --- |
| `0fbf7a9` | Add shared time, asset, and event models |
| `45c7247` | Use structured references in recs/edit |
| `fad4d32` | Move audio arrangements into common Recs documents |
| `ce79588` | Separate arrangement audio ports from file destinations |
| `56cf634` | Add recording and sequence document profiles |
| `67ea823` | Add verified session migration before reader cutover |
| `805fe33` | Save both production conversions and the preparation checkpoint |
| `26f78a5` | Preserve exact audio spans through capture and silence trimming |
| `d5420c9` | Switch session readers and export to common recording documents |

Both user-selected production sessions have new metadata and byte-identical
journal snapshots. All referenced media hashes were checked again after writing;
every audio payload was decoded. Media and original journals were not changed.

| Session | Payloads | Decoded audio frames, summed across files | Unresolved audio placements |
| --- | --- | ---: | ---: |
| [Short](<../../2026-09-04 14-56-53/recording.toml>) | Five empty MIDI files | 0 | 0 |
| [Full](<../../2026-09-04 15-01-57/recording.toml>) | 56 FLAC files and five empty MIDI files | 1,061,479,424 | 39 |

The [full verification report](<../../2026-09-04 15-01-57/migration/report.json>)
lists every mismatch. The old writer computes `quantity_count` as the difference
between timeline endpoints. That is not always the number of frames actually
stored, notably when quiet samples are discarded while a file remains open.
The historical journal does not identify those interior omissions. The new
`unmapped_fragments` records therefore preserve actual payload counts and old
journal ranges separately. They do not invent silence locations, stretch audio,
or treat those files as precisely aligned captures.

The original media remains local operational data. The metadata and journal
snapshots are checked in as migration evidence; checking out this repository
alone does not download the production audio.

The preparation checkpoint passed 914 tests and a second independent verification
of both production payload/hash sets. The cutover adds coverage for reading
silence-trimmed spans, moving a two-volume export away from its original files,
asset integrity failures, and failed finalization recovery. Hardware capture
and live playback have not been run.

Cutover verification: 914 tests pass, plus Ruff, formatting, type checking,
pyupgrade, and diff checks. Both production recordings were read through the
new browser and verified again, decoding all audio and checking every asset's
hash and byte length. Both original journals still match their preserved
snapshots. The editor's rejection of an unresolved production stream was also
checked without rendering or changing production media.

### Current boundary: stage 2 complete

New captures write the version 4 typed append-only journal. Version 3 evidence
is isolated in the explicit historical converter and preserved-journal reader. Finalization builds
typed streams and sealed assets after writers close. Exact audio span offsets
survive buffering and silence trimming, so new captures do not repeat the
historical interior-gap ambiguity. Session readers require `recording.toml`;
there is no automatic old-format fallback. The renderer rejects selected
streams with unresolved placement. Historical audio cannot acquire missing
timing evidence through conversion.

Common continuation links preserve native positions across volumes. Export
copies their complete asset sets, rewrites common-document links, and verifies
hashes, retaining original journal bytes. Recovery reports missing finalized
documents even when the capture journal already has a footer. Diagnostics can
still inspect the operational journal directly with `recs explain`.

Stage 2 now includes:

- Typed audio/event file lifecycle, audio timeline observations, and clock records.
- MIDI timestamps taken in the input callback before queueing, with optional
  exact accumulation of supplied Mido deltas; MIDI-file quantization is export only.
- Native OSC and key events with explicit temporal extents and stable ordinals.
  Raw OSC bytes survive decoding failures and each payload line stands alone.
- Known audio gaps distinguished as silence suppression, missing native ranges,
  or short-capture discard; unobserved intervals remain unknown.
- Immediate finished-file evidence, explicit short-file discard, and stopped
  capture finalization that retains interrupted files and torn tails as partial.
- Persistent event clocks/order across rotation and volume replacement, including
  events buffered while the next volume is unavailable.
- Shared device clocks across tracks, with distinct capture identities after reconnects. Their clock observations
  remain inspectable; editing across independent clocks requires explicit alignment.

The combined acceptance test captures audio, MIDI, and OSC, rotates event files,
changes volumes with queued events, exports the chain, moves the originals away,
verifies payloads, and renders the audio gaps unchanged. Separate tests cover
interrupted and discarded files, native key events, and sub-SMF-tick MIDI timing.
Queued MIDI is drained on shutdown and volume changes; real-time MIDI remains
in native storage and is reported as unsupported by SMF export.
These are file-based tests with fake input sources; physical capture and live
playout have not been exercised. Clock drift fitting and physical latency
calibration are not implied by these observations.

Stage 2 verification: 924 tests pass, plus Ruff, formatting, type checking,
pyupgrade, and diff checks. Both production recordings were verified again:
all asset hashes and byte lengths match, all audio decodes, and both original
journals match their preserved snapshots. The full recording's 39 unresolved
historical placements remain explicit and are rejected by the editor.

Arrangements currently retain file paths, structured source/track selectors, and internal
materialized sources at their preparation boundary. General document dependency
packaging, nested reusable mixes, musical beat clocks, drift fitting, instruments,
DSP graphs, and the sibling application cutovers remain later roadmap work.

## Baseline and proposed ownership

The inventory below comes from local source inspection on 7 September 2026.
Sibling repositories were inspected in their current working trees, so recheck
the named symbols when starting implementation. Existing format models are not
evidence that playback or cross-application execution has been implemented.

Implemented pure definitions now live in `~/code/ufor`, published as
[rec/ufor](https://github.com/rec/ufor). Recs imports the shared document and
encoding types directly; Tuney imports shared musical semantics through its
application configuration adapters. Neither application is required to read a
Ufor document. Reccy remains Python application infrastructure. The old
`recs/model` implementations and Tuney's copied number/accidental modules have
been removed rather than retained as compatibility shims.

Keep specifications, schemas, examples, and language-neutral conformance cases
together with a lightweight Python model implementation. Include pure pitch
and control mathematics where needed to interpret definitions. Runtime sampler
state, device drivers, plugin wrappers, and application UI stay outside the
format core. Use direct imports, no re-export layer in `__init__.py`, and no
device, GUI, NumPy, service, or plugin dependency merely to parse a definition.
Future language ports implement the same semantics, not Python class layouts.

## Existing structures and their replacements

| Existing source | What exists | Proposed change |
| --- | --- | --- |
| [Edit schema](../../recs/edit/schema.py) | `EditSpec`, audio channels, frame clips, gain routes, string automation targets, output encoding | Common arrangement body; named timebases, typed ports, structured addresses; separate exported ports from run destinations |
| [Edit record resolution](../../recs/edit/record.py) | `ResolvedSource`, `AudioFragment`, session selectors, native-rate matching | Resolve typed recording streams/assets; keep native fragments and gap behavior; explicit conversion nodes for mismatched rates |
| [Composition](../../recs/edit/composition.py) | `CompositionEdit`, command recipes, materialized stages | Compile authored operations to nested arrangements/derived assets; retain recipe history as provenance |
| [Session records](../../recs/ui/session_record.py) | Version 4 typed audio/event lifecycle, audio timelines, clock observations, operational events | Implemented; historical version 3 parsing is isolated in explicit migration |
| [Session export](../../recs/ui/session_export.py) | Existing portable session export workflow | Extend its dependency collection to common documents/assets and preserve timeline gaps |
| [Ufor instrument](../../../ufor/ufor/samples/instrument.py) | Common root, body, slots, musical validation | Implemented; Recsam definitions removed |
| [Ufor events](../../../ufor/ufor/events.py) | `Trigger`, `Release`, `ControlChange` | Implemented common tick/ordinal envelope; Recs consumes these directly |
| [Ufor sample types](../../../ufor/ufor/samples/) | Controls, EQ, selection, crossfades, slices, loops, pitch mapping | Implemented with shared envelopes/LFOs/routes; generic DSP remains separate |
| [Ufor SFZ](../../../ufor/ufor/sfz.py), [Recs file adapter](../../recs/recsam/sfz.py) | Pure conversion versus local asset acquisition | Implemented native document conversion, sealed metadata and diagnostics |
| [MIDI writer](../../recs/midi/writer.py), [OSC recorder](../../recs/osc/recorder.py) | Native-timed common event JSONL | Implemented; SMF is explicit export and OSC retains raw bytes alongside decoded values |
| [Lyte show](../../../lyte/lyte/show.py) | `ShowFile`, Python factory lookup, animation/mixer graph | Common graph definitions and installed implementation bindings |
| [Lyte installation](../../../lyte/lyte/installation.py) | Twinkly/DMX targets, pixel/DMX programs, output driver interface | Common definition references plus physical bindings; retain driver implementations |
| [Lyte DMX](../../../lyte/lyte/dmx.py), [Art-Net](../../../lyte/lyte/artnet.py) | Typed categories/values, patch addresses, universe packet encoding | Reusable fixture profiles separate from patch/transport; explicit numbering and quantization |
| [Lyte patches](../../../lyte/lyte/patches.py), [animation](../../../lyte/lyte/animation.py) | Physical regions, MIDI bindings, LED count, render state/arrays | Shared layouts and control mappings; explicit spatial/color types around existing renderers |
| [Streamo config](../../../streamo/streamo/config.py), [services](../../../streamo/streamo/services.py) | Audio device input and streaming-service realization | Programme stream binding alongside application-local delivery configuration; video remains outside the model |
| [Showco models](../../../showco/showco/models.py) | Actions and status snapshots | Keep runtime status models; report common run IDs/observations without making status the content authority |
| [Tuney timing](../../../tuney/tuney/time/char_press.py), [sequencer](../../../tuney/tuney/time/sequencer.py) | Millisecond key events and callback playback | Shared key/performance events and explicit timing conversion at the host boundary |
| [Tuney tuning](../../../tuney/tuney/scale/tuning.py), [scale](../../../tuney/tuney/scale/scale.py) | Tuning functions, note naming, ratio expressions, finite-table host fallback | Extract intended musical semantics in stage 3; explicit repetition and fractional notation; keep host/UI policy separate |
| [Tuney oscillator](../../../tuney/tuney/audio/oscillator.py) | Waveforms, duty cycle, sample-position generation, key-scaled gain | Extract the definition and equations in stage 3; plan reuse of the existing implementation after the waveform-generation deferral |

Sibling source links assume the repositories remain adjacent under `~/code`.

## Decisions to fix before coding the schema

Use the proposal's TOML envelope, discriminated domain bodies, three stream
families, explicit units, native integer timebases, and structured references.
Publish the required field tables and one complete valid example for every
initial document kind. Then generate a JSON Schema from the Pydantic model for
tooling, while TOML remains the canonical authored representation.

Specify which fields are required and which defaults are normative. Mark
absence as inheritance only where the domain defines inheritance, notably
recsam slot settings. Resolve inherited values once during preparation.
Review existing recsam combination rules with before/after examples. Envelopes
and LFOs are explicitly reopened for design; their existing fields are not the
final common model. Select a small coherent profile before implementing it.

Distinguish schema version from capability support. A reader may understand
the document but lack a renderer for one operation. Do not introduce extension
fields that silently bypass validation. A new semantic operation needs a typed
contract and examples before it becomes part of the vocabulary.

## Implementation stages and acceptance gates

### 1. Establish the pure model with audio arrangements

Introduce the common envelope, exact timebases, asset references, typed audio
ports, and arrangement bodies. Refactor existing edit parsing, command output,
graph validation, and rendering to consume that model in one coherent cutover.
Keep the command-line authoring experience where its semantics still apply.

Convert old `sample_rate` to a physical timebase with denominator 1. Preserve
every existing frame position unchanged. Replace selectors with structured
stream/channel references and convert current one-based file channels to
zero-based channel indices once. Replace gain target strings with structured
parameter references; preserve old linear/equal-power audio results through
explicit operations. For `Interpolation.equal_power`, preserve interpolation
of squared gain followed by square root, including the declared gain before
the first knot; do not substitute a different sine/cosine fade convention.
Split file destinations from public bus outputs.

Acceptance: existing edit fixtures retain rendered audio and gap placement;
parse/serialize/parse preserves model meaning; unknown IDs and channel/rate
mismatches fail clearly. Test exact 44.1/48 kHz time conversion separately from
actual resampling. Do not claim universal media support at this stage.

### 2. Adopt recording descriptors and common events

Implemented. The acceptance cases below are covered by local file and fake-input
tests. The native journal and event format are documented in
[Capture journal format](../../doc/session-record-format.md).

Refactor the session journal writer/readers and export path together. Retain
file lifecycle and diagnostic truth while adding typed streams, native timing,
clock mappings, and explicit gap reasons. Record MIDI timing before SMF
quantization. Keep OSC raw bytes and decoded semantics linked rather than
discarding messages that a semantic adapter cannot understand.

Acceptance: one session containing audio, MIDI, and OSC finalizes into portable
documents; counts cannot be confused with duration; packet ordering is stable;
truncated final journal lines and incomplete files remain visibly partial;
volume continuations do not reset the stream timeline. Unit tests should use
in-memory or local file observations, not live networks or hardware.

### 3. Settle and extract the portable musical model

This stage no longer includes sampler implementation or new audio waveform
generation. Work in this order:

Steps 1 through 3 have an implemented initial extraction in Ufor. This includes
finite contiguous tables, repeating ratios and intervals, expression strings,
Scala text conversion, scale naming, and oscillator parameters/equations. The
portable grammar is documented from the stated `/` and `^` requirements; a
separate original grammar implementation was not located. Sparse tuning maps,
MTS byte import and audio oscillator lifecycle integration remain open. Step 4
now has an implemented first modulation profile with scalar conformance cases;
step 5 now has shared performance events, typed routes, the native instrument
root, asset slices, channel maps, source bindings and pure SFZ conversion.
Recsam consolidation is complete. Preparation/action traces remain open. See
[the exact extraction boundary](ufor.md) rather than treating all of stage 3 as
complete.

1. Settle the shared-format ownership and extraction boundary. Capture the
   specification and language-neutral fixtures independently of Python classes.
2. Extract Tuney's intended tuning/scale semantics: finite Hz and ratio tables,
   repeating ratio patterns, explicit reference pitch, spelling, and selection.
   Preserve fractional authoring and the user's frequency/ratio minilanguage
   with `/` and `^`. Locate its grammar and reconcile it with current Tuney
   parsing before implementing it. Specify Scala and MTS adapters explicitly.
3. Extract Tuney's oscillator definition, equations, and parameter behavior.
   Separate waveform shape, phase evolution, and key-scaled gain; record how
   the existing implementation can be reused later without a new renderer now.
4. The first [envelope and LFO profile](modulation.md) now defines timing,
   curves, retrigger/release, scope, phase, and modulation combination. Ufor
   implements the documents and scalar state calculations. Loops, random
   sources, and continuous rate ramps are explicitly deferred. Sample instruments
   now consume the same definitions directly.
5. The [small instrument contract](../../../ufor/doc/instrument-format.md)
   implements the native root, slices, channel maps, source bindings, shared
   events/routes and SFZ conversion. All portable Recsam types now live in Ufor.
   Next settle prepared settings and selection/gate/retirement action traces.
   These stateful additions remain separate from sampler waveform generation.

Acceptance: documents round-trip; exact fractions remain exact; repeating and
finite domains differ explicitly; existing intended Tuney pitch examples agree;
Scala and MTS mappings have defined boundaries; oscillator parameters and
envelope/LFO event/state behavior have language-neutral cases. Numerical pitch
and scalar-control checks are allowed; no new audio rendering is needed to
complete this stage. Record unresolved design choices rather than guess defaults.

### 4. Resume execution only after the model gate

Deferred pending completion of stage 3 and a separate decision to resume audio
generation. Compare a compiled sampler core, an optional Python reference with
a compiled port, and a suitable existing engine. A VST instrument may wrap the
core later. Neither Python-first rendering nor a particular language or plugin
SDK is selected. Define shared conformance cases before implementing either
language, including event order, state, tuning, and modulation behavior.

Use the [deferred playback plan](../sample-playback.md) for the later sampler.
Then generalize the existing renderer's scheduling boundary to typed processors.
Start with acyclic audio/control graphs and existing built-in operations.
Add one concrete installed adapter with a documented parameter mapping, not
simultaneous support for every plugin system. Keep missing implementations
inspectable and unplayable. Use internal-delay operations before exposed cycles.

Acceptance: exact port/range validation; a gain or filter mapping with known
values; latency alignment on parallel paths; audio-to-control timing that
distinguishes observation time from availability; explicit rejection of
unsupported live/offline capabilities. Adapter unit tests check mapping logic;
actual plugin integration and live behavior require separately requested runs.
Later sampler acceptance covers overlapping same-key triggers, sustain/release,
loops, independent instances, and tuning across block sizes. Only after audio
generation resumes add the 48 kHz, at-least-one-second WAV cases, with declared
tolerances comparing reference and compiled implementations where both exist.

Stages 5 through 7 may reuse existing engines and captured media; they must not
implicitly bypass the pause on new waveform generation.

### 5. Integrate Lyte and physical control bindings

Replace Lyte's native show/installation parsing with definitions and bindings
as each entry point is cut over. Reuse its drivers, DMX encoder, region mapping,
and render state. Establish layout IDs, color interpretation, fixture profiles,
physical patching, and control mappings. Do not retain an old parser as a
permanent compatibility path. Add a typed CV endpoint only with a concrete
device and calibration contract.

Acceptance: an envelope from recorded audio drives a light parameter; changing
the physical patch does not edit the timeline; DMX channel collisions and wrong
layouts fail preparation; reference values produce expected packet bytes and
pixel arrays. Packet fixtures can be tested without transmission. Physical
latency, light color, CV range, and disconnect behavior require explicit hardware
verification and must not be inferred from unit-test success.

### 6. Add programme transport and as-aired capture

Implement fixed, follow-on, and bounded cue sections. Give one transport
authority to each run. Integrate Recs recording, Streamo delivery, and Showco
operator actions through their existing operational boundaries. Generate an
as-aired arrangement from observed decisions and captured material.

Acceptance: a deterministic simulated clock exercises a late guest, dropped
relay, replacement material, overrun, cue deadline, and later replay. Future
live input prevents a complete offline render. A recorded as-aired programme
can be rendered without its original live endpoints. Network delivery and
physical playout are separate integration validation, not unit-test claims.

### 7. Complete Tuney's host and synthesis integration

Tuning/scale and oscillator model extraction belongs to stage 3, not this later
stage. Complete authoring, key/performance export, and host integration around
those shared definitions, retaining Tuney's presentation and learning features.
Reuse or move its existing oscillator implementation under the settled contract
when execution work resumes. Do not create duplicate portable schemas or a
parallel waveform engine. Host note-substitution policy remains separate from
the finite tuning tables it consumes.

Acceptance: frequencies agree with existing tuning examples; milliseconds
convert explicitly; selection keys remain independent of pitch; unsupported
device pitch realization is reported instead of silently using equal temperament.

## Cutover and verification discipline

No backward-compatibility layer or automatic historical-document migration is
required. Existing external formats such as SFZ, MIDI, and OSC still need
purposeful import/export adapters because interchange is part of the product.
Update checked-in examples and consumers in each native-format cutover. Old
personal files are outside an implementation commit unless separately selected
for conversion; never bulk-rewrite or delete recording directories.

Each implementation stage must be a usable, tested change, and may need several
small commits. Dependency changes, if required for the chosen implementation,
get their own `pyproject.toml`/`uv.lock` commit. Follow each repository's current
instructions and preserve unrelated worktree changes. Recs requires commits and
pushes for requested edits, and pre-commit verification for Python/data changes:
pytest, targeted Ruff fixes, formatting, type checking, and pyupgrade. Use the
current repository commands and configured Python version when executing them.

For documentation-only changes, check local links, TOML example syntax, internal
consistency, and `git diff --check`. Python and application-data changes require
the verification steps above.

## Existing plans to reconcile when implementing

The [recsam format](../../doc/sample-format.md),
[remaining sample-format work](../sample-format.md), and
[sample-playback plan](../sample-playback.md) remain useful detailed sources.
This master proposal broadens their scope, including generic processing,
shared assets, and tuning dependencies. Reconcile the relevant documents and
remove superseded restrictions when implementing those changes. The playback
and remaining-format plans now explicitly defer rendering and reopen envelope
and LFO design; implemented format documentation remains a description of
current code until a later cutover changes it.
