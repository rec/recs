# Verification procedures

## How to build the common model

### Incomplete

Stage 3 still needs preparation and portable performance-action traces, MIDI
2.0/UMP interchange, and the remaining musical-model decisions. Stages 4–7,
including playback, physical bindings, broadcasts, and Tuney host integration,
are future work.

### Implementation status

Stages 1 and 2 are implemented in Recs. The supported
subset has pure common models, exact rational physical timebases, sealed assets, common event envelopes,
structured source and parameter references, and typed audio ports. Audio editing
now uses the common arrangement score, with file destinations separate from
public outputs. Existing rendered-audio regression behavior is retained.

Recording and sequence scores have a common parser, TOML serializer, and
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
| `fad4d32` | Move audio arrangements into common Recs scores |
| `ce79588` | Separate arrangement audio ports from file destinations |
| `56cf634` | Add recording and sequence score profiles |
| `67ea823` | Add verified session migration before reader cutover |
| `805fe33` | Save both production conversions and the preparation checkpoint |
| `26f78a5` | Preserve exact audio spans through capture and silence trimming |
| `d5420c9` | Switch session readers and export to common recording scores |

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

#### Current boundary: stage 2 complete

New captures write the version 4 typed append-only journal. Version 3 evidence
is isolated in the explicit historical converter and preserved-journal reader. Finalization builds
typed streams and sealed assets after writers close. Exact audio span offsets
survive buffering and silence trimming, so new captures do not repeat the
historical interior-gap ambiguity. Session readers require `recording.toml`;
there is no automatic old-format fallback. The renderer rejects selected
streams with unresolved placement. Historical audio cannot acquire missing
timing evidence through conversion.

Common continuation links preserve native positions across volumes. Export
copies their complete asset sets, rewrites common-score links, and verifies
hashes, retaining original journal bytes. Recovery reports missing finalized
scores even when the capture journal already has a footer. Diagnostics can
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
materialized sources at their preparation boundary. General score dependency
packaging, nested reusable mixes, musical beat clocks, drift fitting, instruments,
DSP graphs, and the sibling application cutovers remain later roadmap work.

### Baseline and proposed ownership

The inventory below comes from local source inspection on 7 September 2026.
Sibling repositories were inspected in their current working trees, so recheck
the named symbols when starting implementation. Existing format models are not
evidence that playback or cross-application execution has been implemented.

Implemented pure definitions now live in `~/code/ufor`, published as
[rec/ufor](https://github.com/rec/ufor). Recs imports the shared score model and
encoding types directly; Tuney imports shared musical semantics through its
application configuration adapters. Neither application is required to read a
Ufor score. Reccy remains Python application infrastructure. The old
`recs/model` implementations and Tuney's copied number/accidental modules have
been removed rather than retained as compatibility shims.

Keep specifications, schemas, examples, and language-neutral conformance cases
together with a lightweight Python model implementation. Include pure pitch
and control mathematics where needed to interpret definitions. Runtime sampler
state, device drivers, plugin wrappers, and application UI stay outside the
format core. Use direct imports, no re-export layer in `__init__.py`, and no
device, GUI, NumPy, service, or plugin dependency merely to parse a definition.
Future language ports implement the same semantics, not Python class layouts.

### Existing structures and their replacements

| Existing source | What exists | Proposed change |
| --- | --- | --- |
| [Edit schema](../../recs/edit/schema.py) | `EditSpec`, audio channels, frame clips, gain routes, string automation targets, output encoding | Common arrangement body; named timebases, typed ports, structured addresses; separate exported ports from run destinations |
| [Edit record resolution](../../recs/edit/record.py) | `ResolvedSource`, `AudioFragment`, session selectors, native-rate matching | Resolve typed recording streams/assets; keep native fragments and gap behavior; explicit conversion nodes for mismatched rates |
| [Composition](../../recs/edit/composition.py) | `CompositionEdit`, command recipes, materialized stages | Compile authored operations to nested arrangements/derived assets; retain recipe history as provenance |
| [Session records](../../recs/ui/session_record.py) | Version 4 typed audio/event lifecycle, audio timelines, clock observations, operational events | Implemented; historical version 3 parsing is isolated in explicit migration |
| [Session export](../../recs/ui/session_export.py) | Existing portable session export workflow | Extend its dependency collection to common scores/assets and preserve timeline gaps |
| [Ufor instrument](../../../ufor/ufor/samples/instrument.py) | Common root, body, slots, musical validation | Implemented; Recsam definitions removed |
| [Ufor events](../../../ufor/ufor/events.py) | `Trigger`, `Release`, `ControlChange` | Implemented common tick/ordinal envelope; Recs consumes these directly |
| [Ufor sample types](../../../ufor/ufor/samples/) | Controls, EQ, selection, crossfades, slices, loops, pitch mapping | Implemented with shared envelopes/LFOs/routes; generic DSP remains separate |
| [Ufor SFZ](../../../ufor/ufor/sfz.py), [Recs file adapter](../../recs/recsam/sfz.py) | Pure conversion versus local asset acquisition | Implemented native score conversion, sealed metadata and diagnostics |
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

### Decisions to fix before coding the schema

Use the proposal's TOML envelope, discriminated domain bodies, three stream
families, explicit units, native integer timebases, and structured references.
Publish the required field tables and one complete valid example for every
initial score kind. Then generate a JSON Schema from the Pydantic model for
tooling, while TOML remains the canonical authored representation.

Specify which fields are required and which defaults are normative. Mark
absence as inheritance only where the domain defines inheritance, notably
recsam slot settings. Resolve inherited values once during preparation.
Review existing recsam combination rules with before/after examples. Envelopes
and LFOs are explicitly reopened for design; their existing fields are not the
final common model. Select a small coherent profile before implementing it.

Distinguish schema version from capability support. A reader may understand
the score but lack a renderer for one operation. Do not introduce extension
fields that silently bypass validation. A new semantic operation needs a typed
contract and examples before it becomes part of the vocabulary.

### Implementation stages and acceptance gates

#### 1. Establish the pure model with audio arrangements

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

#### 2. Adopt recording descriptors and common events

Implemented. The acceptance cases below are covered by local file and fake-input
tests. The native journal and event format are documented in
[Capture journal format](../../doc/session-record-format.md).

Refactor the session journal writer/readers and export path together. Retain
file lifecycle and diagnostic truth while adding typed streams, native timing,
clock mappings, and explicit gap reasons. Record MIDI timing before SMF
quantization. Keep OSC raw bytes and decoded semantics linked rather than
discarding messages that a semantic adapter cannot understand.

Acceptance: one session containing audio, MIDI, and OSC finalizes into portable
scores; counts cannot be confused with duration; packet ordering is stable;
truncated final journal lines and incomplete files remain visibly partial;
volume continuations do not reset the stream timeline. Unit tests should use
in-memory or local file observations, not live networks or hardware.

#### 3. Settle and extract the portable musical model

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
[the exact extraction boundary](verification-procedures.md#ufor-extraction-handover) rather than treating all of stage 3 as
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
4. The first [envelope and LFO profile](deferred-work.md#envelopes-lfos-and-modulation) now defines timing,
   curves, retrigger/release, scope, phase, and modulation combination. Ufor
   implements the scores and scalar state calculations. Loops, random
   sources, and continuous rate ramps are explicitly deferred. Sample instruments
   now consume the same definitions directly.
5. The [small instrument contract](../../../ufor/doc/instrument-format.md)
   implements the native root, slices, channel maps, source bindings, shared
   events/routes and SFZ conversion. All portable Recsam types now live in Ufor.
   Next settle prepared settings and selection/gate/retirement action traces.
   These stateful additions remain separate from sampler waveform generation.
6. Define MIDI interchange before extending device-specific MIDI work. Keep
   semantic performance/control events independent of their wire encoding;
   specify MIDI 1.0 byte streams and UMP separately, including UMP-carried
   MIDI 1.0, native MIDI 2.0 messages, group assignment, SysEx7 and SysEx8.
   Make MIDI 1.0 conversion an explicit capability-limited operation. Keep
   MIDI-CI discovery, Profiles and Property Exchange as device interaction and
   binding information, not universal instrument fields. The existing VL70m
   SysEx work is a bounded MIDI 1.0 proof of concept, not this layer.

Acceptance: scores round-trip; exact fractions remain exact; repeating and
finite domains differ explicitly; existing intended Tuney pitch examples agree;
Scala and MTS mappings have defined boundaries; oscillator parameters and
envelope/LFO event/state behavior have language-neutral cases. Numerical pitch
and scalar-control checks are allowed; no new audio rendering is needed to
complete this stage. MIDI acceptance cases preserve raw MIDI 1.0 bytes and UMP
words exactly, make protocol conversion limits visible, and retain unfamiliar
SysEx7/SysEx8 packets without inventing semantic fields. Record unresolved
design choices rather than guess defaults.

#### 4. Resume execution only after the model gate

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

#### 5. Integrate Lyte and physical control bindings

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

#### 6. Add programme transport and as-aired capture

Implement fixed, follow-on, and bounded cue sections. Give one transport
authority to each run. Integrate Recs recording, Streamo delivery, and Showco
operator actions through their existing operational boundaries. Generate an
as-aired arrangement from observed decisions and captured material.

Acceptance: a deterministic simulated clock exercises a late guest, dropped
relay, replacement material, overrun, cue deadline, and later replay. Future
live input prevents a complete offline render. A recorded as-aired programme
can be rendered without its original live endpoints. Network delivery and
physical playout are separate integration validation, not unit-test claims.

#### 7. Complete Tuney's host and synthesis integration

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

### Cutover and verification discipline

No backward-compatibility layer or automatic historical-score migration is
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

### Existing plans to reconcile when implementing

The [recsam format](../../doc/sample-format.md),
[remaining sample-format work](../sample-format.md), and
[sample-playback plan](../sample-playback.md) remain useful detailed sources.
This master proposal broadens their scope, including generic processing,
shared assets, and tuning dependencies. Reconcile the relevant documents and
remove superseded restrictions when implementing those changes. The playback
and remaining-format plans now explicitly defer rendering and reopen envelope
and LFO design; implemented format documentation remains a description of
current code until a later cutover changes it.


## Recs: a common language for things that happen in time

### Incomplete

Stage 3 still needs portable preparation and performance-action traces, MIDI
2.0/UMP interchange, and the remaining model decisions named in
[How to build the common model](verification-procedures.md#how-to-build-the-common-model). Playback, device bindings,
lighting, broadcasts, synthesis, and the still-image slideshow player remain
future work.

### The central decision

Use one score envelope and typed composition model, with distinct payloads
for genuinely different data. A note release is an event; a voltage is a
quantity; a light field also has geometry. Making everything an audio buffer,
a MIDI message, or a dictionary of arbitrary values would discard meaning.

An object exposes typed input and output ports and named parameters. Its
definition can be a recording, sequence, arrangement, sample instrument,
processor graph, or live endpoint. Other objects refer to that public interface.
A mix can contain another mix without knowing its internal tracks. An instrument
can drive audio and lighting through separate, explicitly typed routes.

Keep three things distinct:

1. **Definition:** what the work means, its assets, timing, connections, and
   musical or physical parameters.
2. **Binding:** which installed implementation or physical endpoint will realize
   that definition, including parameter and channel mappings.
3. **Run record:** what actually happened, including clock observations, live
   material, failures, operator actions, and rendered assets.

This is a file format and execution contract, not a replacement plugin ABI,
network protocol, operating system, or database.

### Score map

| Score | Subject |
| --- | --- |
| [Time](verification-procedures.md#time-clocks-and-transport) | Exact time, beats, clocks, synchronization, and scheduling |
| [Quantities](future-proposals.md#sampled-quantities-curves-and-physical-controls) | Sampled audio, control curves, CV, gates, and measured features |
| [Events](future-proposals.md#events-requests-and-sequences) | Notes, MIDI, keys, OSC, requests, and sequence semantics |
| [Recordings](verification-procedures.md#recordings-assets-and-portable-files) | Assets, stream fragments, gaps, capture journals, and packaging |
| [Instruments](deferred-work.md#sample-instruments-and-performance-objects) | Sample instruments, voices, layers, and performance controls |
| [Processors](deferred-work.md#synthesizers-dsp-and-analysis-graphs) | Synthesizers, DSP, analysis, and typed processing graphs |
| [Modulation](deferred-work.md#envelopes-lfos-and-modulation) | Envelope and LFO design before new rendering engines |
| [Arrangements](future-proposals.md#arrangements-sequences-and-nested-mixes) | Clips, tracks, buses, automation, and nested mixes |
| [Broadcasts](future-proposals.md#radio-programmes-live-sections-and-rebroadcast) | Future programmes, live sections, live relays, and rebroadcast |
| [Lighting](future-proposals.md#fixture-controls-dmx-and-spatial-light-fields) | Fixture state, DMX/Art-Net, pixel fields, and geometry |
| [Bindings](future-proposals.md#implementations-endpoints-and-parameter-mappings) | Implementations, device profiles, parameter translation, and limitations |
| [Tunings](deferred-work.md#pitch-tunings-and-scales) | Pitch, scales, and the connection to Tuney |
| [Live slideshow](future-proposals.md#live-slideshow-format) | Timed visual assets, accompaniment, accessibility, and live presentation |
| [New formats](future-proposals.md#new-data-domains-and-interchange-formats) | Candidate editable domains and their existing interchange formats |
| [How to implement](verification-procedures.md#how-to-build-the-common-model) | Current structures, replacements, ownership, and staged work |
| [Future features](future-proposals.md#future-features-worth-building) | Candidate work beyond the first usable system |

Wholly completed documents move to [complete/](complete/README.md). None has
reached that state yet; documents that mix implemented and remaining work put
their unfinished boundary first.

### A small common vocabulary

The proposed root is `Score`, serialized as TOML. Use `format = "recs"`,
integer `version = 3`, a stable `name`, a human `title`, and optional `tags`.
Domain score types select their own body. This version is independent of
existing recsam and edit versions.
The initial kinds are `recording`, `sequence`, `instrument`, `processor`,
`arrangement`, `broadcast`, `binding`, `layout`, and `tuning`.

The envelope can carry `timebases`, `assets`, `dependencies`, `ports`, and
`parameters` collections, each empty when unused. A required `body` is selected
by `kind` and contains that domain's fields. A processor body may contain a
live endpoint node whose realization requires a binding. A recording exposes
its selected streams as declared output ports. This keeps endpoint references
and recording references consistent with other reusable objects.

| Structure | Required meaning |
| --- | --- |
| `Timebase` | ID and exact rational ticks per second, or ticks per quarter note with a tempo map |
| `StreamType` | Payload family, semantic schema, unit where numeric, shape/layout, and timebase |
| `Port` | Stable ID, direction, stream type, and declared combination rule if it accepts multiple connections |
| `Parameter` | Stable ID, type, unit/domain, default, permitted range or choices, scope, and automation policy |
| `Asset` | ID, relative path, encoding, and payload description; sealed assets also have byte length and SHA-256 |
| `ScoreVersion` | Relative score path or selector, with an optional digest of the selected score's exact bytes |
| `Node` | ID, referenced definition or registered primitive, and parameter values |
| `Connection` | Explicit source node/port and destination node/port references |
| `Binding` | Realization of a definition or endpoint with a declared capability contract |
| `RunRecord` | Definition identity, resolved dependencies/bindings, observations, and produced assets |

Use three stream families: `sampled` for regular arrays, `curve` for timed
numeric knots, and `event` for discrete typed records. Semantic schemas refine
these: audio PCM, pitch estimates, performance events, raw MIDI, fixture state,
and pixel fields have different contracts even when their storage families match.
Static definitions such as layouts and tunings are score dependencies, not
pretend streams with one value per audio frame.

Public ports are the complete interface. A reference to an arrangement reads
its named exported port, never a private bus guessed from a filename. Parameter
addresses use structured `{node, parameter}` references; port addresses use
`{node, port}`. An exported parameter explicitly delegates to one internal
parameter. A macro affecting several parameters is a mapping processor.

Names are unique in their declared collection and remain stable through title
edits. Imports are namespaced by dependency name. Reference cycles between
scores are invalid; signal feedback has separate rules in [Processors](deferred-work.md#synthesizers-dsp-and-analysis-graphs).
No implicit merging of equally named objects occurs.

### Serialization and editing

TOML holds definitions, small curves, and short authored sequences. Bulk
payloads are assets described in [Recordings](verification-procedures.md#recordings-assets-and-portable-files). Reuse the same
typed event records in inline `events` and recorded JSONL; these are storage
forms of one model, not different sequence languages. A stream chooses one
storage form. Files are relative to their containing score; portable export
collects dependencies under one directory and rewrites references.

Use tagged Pydantic models with explicit fields, frozen definitions, and list
or dict collections. Keep runtime handles and mutable state out of scores.
Unknown required kinds, operations, or fields are validation errors. Vendor
parameters belong in a typed binding profile, rather than unchecked keys in
the common schema. Opening and editing a definition must not load plugin code,
connect to devices, or execute Python or shell text.

The examples in this directory are proposed TOML fragments unless explicitly
identified as complete. Names such as `recs.gain` describe proposed operation
contracts, not import paths or currently available commands. Complete required
fields and machine-readable schemas are an implementation deliverable in
[How to implement](verification-procedures.md#how-to-build-the-common-model); these scores fix the important semantics first.

### What uniformity promises

A conforming reader can inspect, validate, and edit the definition without its
original devices. A capable host can realize its selected graph. Unsupported
operations remain visibly unsupported; they are not silently omitted or
substituted. A resolved run states which capabilities were required and used.

Identical parameter names do not promise identical sound, color, or timing.
A compressor threshold and ratio do not specify its detector or transfer curve.
For reproducible results, retain a precise implementation binding and initial
state, or capture the produced streams. Distinguish semantic interchange from
reproducing a particular performance.

### Application responsibilities

| Application | Role in the proposed system |
| --- | --- |
| Ufor | Common definitions, pure musical mathematics, codecs, schemas, and portable conformance cases |
| Recs | Capture, asset preparation, timeline editing, verification, and eventual playback transport |
| Lyte | Lighting generators, fixture and geometry interpretation, and physical lighting outputs |
| Streamo | Live stream input/output adapters and broadcast delivery; its existing video features stay outside this format |
| Showco | Installation coordination, bindings, operator controls, and observable run status |
| Tuney | Tuning/scale authoring and experiments; provide explicit pitched performance and synthesis definitions |

The implemented shared definitions live in `~/code/ufor`, published as
[rec/ufor](https://github.com/rec/ufor). Recs and Tuney consume that shared core
through direct imports. Tuney's UI and existing waveform generation, Recs's
capture and file-verification operations, and Reccy's application infrastructure
remain in their own projects. See the [extraction handover](verification-procedures.md#ufor-extraction-handover) for the
implemented boundary and remaining design work.

### First useful result

Stages 1 and 2 already cover arrangements and native capture. Tuning, scale,
oscillator, envelope, and LFO definitions now have portable Ufor models and
musical or scalar/state conformance cases. The instrument contract now includes
shared performance events, typed routes, native instrument scores and SFZ
conversion. Next settle preparation and portable voice-action traces. Design the
sampler's interface without selecting its implementation language or producing
new audio. Later rendering and a possible VST realization require the model
gate to pass and a separate implementation decision. Cross-domain control and
broadcast work can reuse existing recordings and engines. Each stage has its
own acceptance gate in
[How to implement](verification-procedures.md#how-to-build-the-common-model).

### Additional work beyond the prompt

None.


## Recordings, assets, and portable files

### Incomplete

Dense-array streams and general score-dependency packaging remain proposals
for later stages. The current completed profile covers capture journals and
recording metadata, not a general portable package implementation.

### Recording score

A recording contains stream descriptors, clock observations, fragments, gap
records, and asset references. Each stream has a stable ID, source endpoint
identity, semantic type, and native timebase. Fragments declare `asset`,
`asset_start`, native `start`, and `count`; sampled counts mean frames, while
event fragments declare their event count and explicit temporal extent.
Never use the same count field as both event quantity and elapsed time.

Each gap declares its interval and reason, such as silence suppression, input
overflow, disconnected device, or unavailable source. Silence suppression means
an intentional omission under a recorded threshold policy, not exact knowledge
that every sample was zero. Unknown duration remains unknown, with boundary
observations; do not manufacture an exact gap length.

Illustrative recording fragments:

```toml
[[streams]]
id = "desk"
family = "sampled"
schema = "recs.audio"
timebase = "desk-clock"
channels = ["left", "right"]

[[streams.fragments]]
asset = "take-a"
asset_start = 0
start = 0
count = 48000

[[streams.gaps]]
start = 48000
end = 96000
reason = "input_overflow"

[[streams.fragments]]
asset = "take-b"
asset_start = 0
start = 96000
count = 48000
```

With a 48 kHz native clock, this is a three-second timeline containing two
seconds of captured audio. The missing second does not slide the second file
earlier. Alternate encodings of the same interval share an explicit variant
group; they are not overlapping takes to mix together.

### Payload storage

Use TOML for authored definitions. Reuse existing audio codecs and simple
sidecar formats rather than inventing a universal binary container:

| Payload | Initial storage |
| --- | --- |
| Audio samples | WAV/FLAC or another explicitly supported codec, with decoded frame metadata |
| Dense numeric control or pixel arrays | Non-object NPY arrays, with semantic axes, unit, layout, and clock in the recording score |
| Recorded events and raw packets | UTF-8 JSONL with the shared event schema; binary fields use base64 |
| Small authored curves and sequences | Inline typed TOML records |
| Plugin-specific state | Opaque asset with implementation identity and declared encoding |

NPY is a proposed initial array encoding because these projects already use
NumPy; object arrays and pickle loading are excluded. Rotation produces bounded
array fragments rather than a single indefinitely growing array. An exchange
reader needs only the encodings used by its selected streams.

Assets declare decoded shape/rate where applicable. Sealed assets have SHA-256
and byte length so edits cannot silently reuse changed content. A path locates
an asset; its digest identifies those bytes. A re-encoded file has a new digest
even if its decoded samples are identical. Keep source lineage separately.

### A run while it is still happening

Definitions are immutable inputs to a run. Use an append-only JSONL journal for
fragment start/finish, clock observations, gaps, requests/results, operator
decisions, and errors. This extends the useful pattern of the existing Recs
session record rather than rewriting TOML on every audio block.

Only a finished fragment with verified metadata becomes a sealed asset.
An interrupted fragment remains partial. Recovery accepts complete journal
records up to a torn final line and reports that line; corrupt interior records
remain errors. Finalization produces a recording score and preserves the
journal as provenance. A recording that is still open is explicitly marked open
and exposes only verified completed fragments to an ordinary offline reader.

For recording across removable volumes, preserve stable stream IDs and explicit
continuation links. Consolidated portable export collects the selected fragments
and preserves the original timeline, including gaps and continuation history.

### Portable package

Use an ordinary directory containing a root TOML score, dependent scores,
assets, and run journals. References must remain inside the exported root after
path and symlink resolution. Import and authoring may select external local
files, but portable export copies the dependency closure and rewrites paths.
Do not embed credentials, machine sockets, or transient in-memory IDs.

Keep live endpoint requirements in the package as logical interfaces. A future
microphone feed has no asset hash; a completed capture replacing it does. A
missing dependency is an actionable validation error and not permission to
search the network for a vaguely similar replacement.

### Change from today

The original `SessionHeader` version 3, `FileRecord`, and `EventRecord` in
`recs/ui/session_record.py` already capture stream identity, file lifecycle,
quantities, and diagnostic events. Replace their optional audio/MIDI/OSC field
mixture with typed stream and observation records. Keep the journal write and
recovery behavior where suitable. Replace `SOURCE:TRACK[:OFFSET]` parsing in
`recs/edit/record.py` with structured stream and channel references.

`AudioFragment` and `ResolvedSource` remain useful runtime concepts, but resolved
paths, loaded buffers, and estimated clocks must not become the portable source
definition. Extend the existing session export workflow rather than adding a
second export path with different containment and gap semantics.

### Implemented stage 2 profile

Current captures use typed version 4 journal records, native MIDI/OSC/key JSONL,
measured clock observations, and explicit audio gap evidence. See the normative
[recording score](../../doc/recording-format.md) and
[capture journal](../../doc/session-record-format.md) profiles. Dense arrays and
general score dependency packaging above remain proposals for later stages.


## Time, clocks, and transport

### Incomplete

Portable scheduling, checkpoint restoration, real-time lateness policies, and
cross-machine clock synchronization remain execution work. Capture timebases,
clock observations, and native event timing are the completed foundation.

### Exact positions

Store integer ticks in a named timebase. A physical timebase declares a positive
rational rate `{numerator, denominator}` in ticks per second. Audio at 48 kHz
uses 48,000/1; a 44.1 kHz asset keeps 44,100/1. A device clock and a timeline
timebase are distinct: the first is a measured oscillator, the second is a
coordinate system.

A position is `{timebase = "audio", tick = 48000}`. A duration has the same
shape but is an interval, not an absolute position. Within a stream or clip
that declares its timebase, its integer positions inherit that timebase.
Positions are signed to permit pre-roll; payload array offsets remain
nonnegative. All stored ranges are half-open `[start, end)`.

For rate `n/d`, tick `k` represents exactly `k*d/n` seconds from its origin.
Do rational arithmetic between timebases. Convert an event to a destination
sample frame once, using nearest integer with ties to even. Keep its original
position in the source score; never round each elapsed delta independently.
For example, tick 44,100 at 44.1 kHz maps exactly to frame 48,000 at 48 kHz.
Two seconds of output always span exactly 96,000 output frames.

Sampled streams at different rates require a declared resampler. Changing a
timestamp does not resample an array. A host uses one scheduling timeline and
explicit converters at rate boundaries, rather than imposing 48 kHz on every
kind of data.

### Musical time

A musical timebase declares integer ticks per quarter note and a tempo map.
Start with piecewise constant tempo segments whose positive quarter-note
duration is a rational number of seconds. Store time signatures separately for
bar/beat display. Tempo ramps can follow when their integration rule is specified.

```toml
[[timebases]]
id = "beats"
kind = "musical"
ticks_per_quarter = 960

[[timebases.tempo]]
tick = 0
seconds_per_quarter = { numerator = 1, denominator = 2 }

[[timebases.tempo]]
tick = 7680
seconds_per_quarter = { numerator = 2, denominator = 3 }
```

The first eight quarters last four seconds; the next quarter ends at 14/3
seconds. Tempo applies from the segment's tick onward. A map begins at or
before the earliest musical position it resolves. Edits preserve beat positions
when changing tempo; physically timed recordings do not stretch implicitly.
Freeze a selected tempo map in the run record.

### Capture clocks and synchronization

Each capture stream names a clock. Clock observations contain source tick,
session tick, timing source, and uncertainty. Multiple observations describe
piecewise affine mappings to the session timeline, including measured drift.
Clock discontinuities start new segments; never fit a single mapping across a
reset. Preserve native counts even when a host estimates a better alignment.

Arrival time, source-provided time, and scheduled execution time are separate
fields when available. A host-monotonic arrival stamp is useful evidence but
does not prove when the remote device produced the data. Record the capture
origin for process-local clocks so stored monotonic values remain interpretable.

Absolute UTC anchors connect a timeline position to a date for broadcasts and
logs. Wall-clock corrections must not make running playback jump. Resolve a
scheduled UTC start to the host's monotonic clock, record the decision, and
report subsequent clock error. Cross-machine synchronization needs measured
offset and drift; a shared format alone cannot synchronize devices.

OSC bundles carry execution timetags, but OSC does not provide clock
synchronization. Preserve bundle time independently of reception time.
[OSC 1.0 specification](https://opensoundcontrol.stanford.edu/spec-1_0.html).

### Scheduling and state

Events carry an integer ordinal unique within their stream. Sort by resolved
time and then ordinal. Merging streams uses the connection's declared input
order before each stream's ordinal for ties. Do not silently reorder note-off
and note-on messages because their timestamps coincide.

Playback owns position, start/stop/pause, loop boundaries, and initial state.
Before seeking, stop voices owned by the previous transport position, restore
state from a declared checkpoint or replay from the beginning, and suppress
external actions during reconstruction. Stateful DSP needs pre-roll or a
checkpoint; it cannot generally start at an arbitrary clip boundary unchanged.

Real-time sinks declare acceptable lateness and an explicit action for late
data. Events that end a note need different handling from a stale pixel frame.
Queues are bounded; a discarded quantity or event produces a run observation.
Offline rendering has no lateness and uses the same ordering and state rules.
Processor latency, analysis lookahead, and output latency are accounted for
separately; alignment cannot give a live process advance knowledge of input.

### Change from today

`EditSpec.sample_rate` and its frame positions already provide exact audio
timing. Preserve those counts while moving the rate into a named timebase.
Recsam events currently inherit an output-frame clock; give them a sequence
timebase. MIDI capture in `recs/midi/writer.py` currently quantizes deltas into
SMF ticks. Record native timing first and make SMF a deliberate export.
Tuney's `CharPress.time` is in milliseconds; convert it explicitly rather than
reinterpreting that number as sample frames.


## Ufor extraction handover

### Incomplete

Portable preparation and performance-action traces, sparse tunings and MTS
byte import, oscillator lifecycle integration, and MIDI 2.0/UMP interchange
remain model work. No sampler, waveform renderer, plugin host, or VST exists.

### Ownership

| Owner | Implemented responsibility |
| --- | --- |
| Ufor | Timebases, assets, references, stream/encoding types, events, recordings, sequences, arrangements, score codec and schema |
| Ufor | Frequency/ratio expressions, computed tuning, finite frequency and ratio tables, repeating ratios and adjacent intervals, Scala text conversion, scale naming, accidentals, and oscillator parameters/gain |
| Ufor | Segmented envelope and LFO scores, exact control-clock coordinates, event/state calculations, scalar shape/curve observations, and modulation conformance cases |
| Ufor | Shared performance events in native sequences/JSONL; typed parameter/source/route declarations and scalar route evaluation |
| Ufor | Native sample-instrument scores, asset slices, explicit channel maps, controls/selection/chokes/articulations/EQ, generator bindings, and pure SFZ conversion |
| Ufor | Lossless VL70m MIDI 1.0 SysEx inspection and bounded patch relocation, retaining opaque message spans and duplicate occurrences |
| Recs | Capture, journals, finalization, verification, media I/O, session migration, editing and existing rendering |
| Tuney | Editable configuration and UI annotations, units and broader expressions, Scala file/browser access, instrument-range wrapping, MIDI protocol delivery, and existing NumPy waveform generation |
| Reccy | Shared Python application infrastructure, with no ownership of the portable format |

The old `recs.model` implementations are removed. Direct imports use the defining
`ufor` module, including `ufor.encoding.Format` and `Subtype`. The core model
tests moved to Ufor; Recs retains its application integration tests. Tuney's
Scale and Oscillator classes add UI fields/runtime realization to Ufor models;
its computed/ratio/table/tuning configurations compile to Ufor definitions.

### Scores and musical semantics

[The musical specification](../../../ufor/doc/musical-format.md),
[JSON Schema](../../../ufor/schema/scores.json), and
[language-neutral conformance cases](../../../ufor/conformance/pitch.json)
live with the implementation. The common codec handles recording, sequence,
arrangement, tuning, scale, oscillator, envelope, LFO and instrument scores. The
[modulation profile](../../../ufor/doc/modulation-format.md) specifies the new
control models now used directly by sample instruments. Recs now imports performance
events directly from `ufor.events`; its old `recs/recsam/events.py` is removed.
The [instrument contract](../../../ufor/doc/instrument-format.md) specifies
the implemented native instrument/SFZ cutover and its remaining preparation
boundary. All portable Recsam definitions and pure SFZ conversion now live
in Ufor; Recs retains only asset and SFZ file acquisition.

Frequency tables never wrap. Tuney explicitly wraps keys within an instrument's
configured range before consulting its finite definition. Ratio tables are
finite unless they declare a repeat multiplier. Adjacent interval patterns
declare whether they repeat; one `2^(1/12)` interval is a one-step equal-tempered
pattern. Fractions such as `5/4` and `2/3` remain valid human-readable values.

The portable grammar supports numbers, division, powers, signs and parentheses.
It records the user's stated `/` and `^` behavior; no separate original grammar
implementation was found. Tuney retains its broader math authoring language and
also accepts `^`. Scala imports distinguish integer ratios from decimal cents.
Finite MTS tables have an explicit representation, but MTS byte decoding and
sparse update messages are not part of this extraction.
The VL70m proof of concept is intentionally MIDI 1.0 byte-stream only. UMP,
native MIDI 2.0 messages, SysEx8, MIDI-CI, Profiles, and Property Exchange need
their own transport and capability design before Ufor adds further
device-specific MIDI descriptions.

`Computed.limit` retains its actual maximum-denominator behavior. The earlier
Tuney comment calling it N-limit just intonation was inaccurate. Oscillator
gain retains its twelve-key-step convention independently of tuning period.

### Installation and verification

For sibling development, clone Ufor beside Recs and Tuney, then run `uv sync`
in each application. Ordinary package installations use the pinned public
archive; `UV_NO_SOURCES=1` release builds also use it. The archive was tested in
an isolated environment with no Recs, Tuney, Reccy, NumPy, audio, or GUI packages.

Checks passed: 65 Ufor tests, 892 Recs tests, and 513 Tuney tests, plus Ruff,
formatting, type checking and Python syntax modernization. Existing audio
regressions remain unchanged. These counts describe the initial extraction;
the subsequent modulation milestone passes 132 Ufor tests, including 67 new
modulation checks, plus Ruff, formatting, type checking, and pyupgrade.
The performance/route milestone passes 192 Ufor tests and 865 Recs tests,
plus those static checks. Thirty shared event tests moved from Recs into Ufor;
Recs retains instrument-specific event validation tests. Tuney was not changed
or retested in this milestone.
The completed Recsam consolidation passes 306 Ufor tests and 741 Recs tests,
plus Ruff, formatting, type checking, pyupgrade and diff checks. The wheel
contains all 35 Python modules. Pure musical/model tests now live in Ufor;
Recs retains SFZ file/asset integration tests, including byte-preserving import
and symlink containment. No production media was touched in this consolidation.
Ufor has no GitHub workflows, as requested. Automated checks do not
claim live hardware or packaged application validation.

Both production recordings were verified again with Ufor-owned models. The
short recording has five MIDI files; the full one has 56 audio files and five
MIDI files. Media and original journals were unchanged. The full recording's
39 unresolved audio placements remain explicit and are still rejected when
selected for timeline editing. This extraction preserves the `format = "recs"`
marker and version 1, so it requires no new production metadata migration.

### What remains

The first envelope/LFO profile, shared performance events, typed routes, native
instrument root, slices, channel maps, source bindings and SFZ conversion are
implemented. Next define resolved preparation settings and portable
selection/gate/retirement action traces. These stateful components never existed
in Recsam and are not part of the completed type consolidation. Sparse tuning
maps, Scala keyboard mapping, MTS byte import, audio oscillator lifecycle
integration, the MIDI 2.0/UMP interchange layer, and richer cross-domain graphs
remain future model work. No sampler engine,
new waveform renderer, compiled-language implementation, or VST was added.
Existing implementations can realize later contracts after an explicit design
and conformance decision. Stage 3 as a whole is not yet complete.

### Additional work beyond the prompt

None.
