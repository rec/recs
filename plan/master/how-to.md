# How to build the common model

Part of the [master proposal](master.md). This is an implementation sequence,
not permission to change runtime code as part of the documentation task.
Additional work beyond the prompt: None.

## Baseline and proposed ownership

The inventory below comes from local source inspection on 7 September 2026.
Recs HEAD at inspection was `6e79423` (`Add daemon status watch`). Sibling
repositories were inspected in their current working trees, so recheck the
named symbols when starting implementation. Existing format models are not
evidence that playback or cross-application execution has been implemented.

Place pure format definitions in proposed `recs/model/` modules for documents,
time, streams, assets, events, parameters, graphs, and typed domain bodies.
Initially keep Recs as their owner. Use explicit imports from defining modules
and no re-export layer in `__init__.py`. Depend on Pydantic and lightweight
standard-library types; never import recording devices, GUI code, services,
NumPy buffers, or plugin libraries merely to parse a definition.

Move domain-specific reusable definitions into that package when their cutover
is implemented. Runtime sampler state, Lyte renderers/drivers, Streamo delivery,
Showco operational views, and Tuney's UI remain with their respective owners.
If depending on Recs prevents a lightweight consumer installation, propose a
separate format distribution at that point. Do not preemptively add another
repository or duplicate the model in every application.

## Existing structures and their replacements

| Existing source | What exists | Proposed change |
| --- | --- | --- |
| [Edit schema](../../recs/edit/schema.py) | `EditSpec`, audio channels, frame clips, gain routes, string automation targets, output encoding | Common arrangement body; named timebases, typed ports, structured addresses; separate exported ports from run destinations |
| [Edit record resolution](../../recs/edit/record.py) | `ResolvedSource`, `AudioFragment`, session selectors, native-rate matching | Resolve typed recording streams/assets; keep native fragments and gap behavior; explicit conversion nodes for mismatched rates |
| [Composition](../../recs/edit/composition.py) | `CompositionEdit`, command recipes, materialized stages | Compile authored operations to nested arrangements/derived assets; retain recipe history as provenance |
| [Session records](../../recs/ui/session_record.py) | Header v3, file lifecycle, optional media-specific fields, operational events | Typed recording journal, stream descriptors, clock observations, and finalized recording documents |
| [Session export](../../recs/ui/session_export.py) | Existing portable session export workflow | Extend its dependency collection to common documents/assets and preserve timeline gaps |
| [Recsam instrument](../../recs/recsam/instrument.py) | `SampleInstrument`, `Instrument`, `SampleSlot`, musical validation | Common root/interface and shared assets; retain specialized slot semantics |
| [Recsam events](../../recs/recsam/events.py) | `Trigger`, `Release`, `ControlChange` | One shared performance family plus common time/ordinal envelope |
| [Recsam controls](../../recs/recsam/controls.py), [processing](../../recs/recsam/processing.py), [playback](../../recs/recsam/playback.py) | Polarity/defaults, EQ, envelopes, LFOs, loops, pitch mapping | Common parameter identities/units; preserve voice behavior and native-frame ranges; general DSP through processor contracts |
| [Recsam SFZ](../../recs/recsam/sfz.py) | External sample-format adapter | Target the new instrument body; preserve explicit unsupported-feature reporting |
| [MIDI writer](../../recs/midi/writer.py), [OSC recorder](../../recs/osc/recorder.py) | SMF recording and packet-oriented JSONL capture | Native-timed raw capture plus optional semantic projections; SMF becomes export |
| [Lyte show](../../../lyte/lyte/show.py) | `ShowFile`, Python factory lookup, animation/mixer graph | Common graph definitions and installed implementation bindings |
| [Lyte installation](../../../lyte/lyte/installation.py) | Twinkly/DMX targets, pixel/DMX programs, output driver interface | Common definition references plus physical bindings; retain driver implementations |
| [Lyte DMX](../../../lyte/lyte/dmx.py), [Art-Net](../../../lyte/lyte/artnet.py) | Typed categories/values, patch addresses, universe packet encoding | Reusable fixture profiles separate from patch/transport; explicit numbering and quantization |
| [Lyte patches](../../../lyte/lyte/patches.py), [animation](../../../lyte/lyte/animation.py) | Physical regions, MIDI bindings, LED count, render state/arrays | Shared layouts and control mappings; explicit spatial/color types around existing renderers |
| [Streamo config](../../../streamo/streamo/config.py), [services](../../../streamo/streamo/services.py) | Audio device input and streaming-service realization | Programme stream binding alongside application-local delivery configuration; video remains outside the model |
| [Showco models](../../../showco/showco/models.py) | Actions and status snapshots | Keep runtime status models; report common run IDs/observations without making status the content authority |
| [Tuney timing](../../../tuney/tuney/time/char_press.py), [sequencer](../../../tuney/tuney/time/sequencer.py) | Millisecond key events and callback playback | Shared key/performance events and explicit timing conversion at the host boundary |
| [Tuney tuning](../../../tuney/tuney/scale/tuning.py), [scale](../../../tuney/tuney/scale/scale.py), [oscillator](../../../tuney/tuney/audio/oscillator.py) | Tuning functions, note naming, waveform generation | Pure tuning documents and synthesis bindings; retain educational UI and runtime implementation locally |

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
Keep all present recsam combination rules until an intentional change is
specified with before/after examples. This proposal does not justify changing
those rules simply to simplify serialization.

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

### 3. Adopt instruments and implement offline performance

Move common performance events and parameter descriptors to the shared model.
Replace recsam's native root and path fields; update all imports, documentation,
SFZ adapter calls, and fixtures in the same cutover. Preserve selection,
articulation, loop, sustain, pitch, and local modulation semantics.

Implement the stateful sampler described in the
[existing playback plan](../sample-playback.md), using one event contract for
offline and eventual live hosts. Before adding voice limits, linked microphone
layers, or stochastic behavior, finalize the precise interactions identified
in [Instruments](instruments.md). Deterministic ordered selection can come first.

Acceptance: render overlapping same-key triggers, sustain/release, loop exits,
independent instrument instances, and non-default tuning without changing their
meaning at different block sizes. Digital-audio regression fixtures write WAV
at 48,000 Hz and last at least one second, following repository instructions.

### 4. Add processor graphs and one external implementation

Generalize the existing renderer's scheduling boundary to typed processors.
Start with acyclic audio/control graphs and existing built-in operations.
Add one concrete installed adapter with a documented parameter mapping, not
simultaneous support for every plugin system. Keep missing implementations
inspectable and unplayable. Use internal-delay operations before exposed cycles.

Acceptance: exact port/range validation; a gain or filter mapping with known
values; latency alignment on parallel paths; audio-to-control timing that
distinguishes observation time from availability; explicit rejection of
unsupported live/offline capabilities. Adapter unit tests check mapping logic;
actual plugin integration and live behavior require separately requested runs.

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

### 7. Integrate Tuney's authoring and synthesis

Export exact tuning/scale definitions and key/performance sequences. Bind its
oscillator behavior to the processor interface where useful. Remove duplicate
portable event/tuning schemas when adopting the common ones, while retaining
Tuney's application-specific presentation and learning features.

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

For this documentation-only task, check local links, TOML example syntax,
internal consistency, and `git diff --check`. Do not run the application or
Python test suite, since no Python code or application data changes.

## Existing plans to reconcile when implementing

The [recsam format](../../doc/sample-format.md),
[remaining sample-format work](../sample-format.md), and
[sample-playback plan](../sample-playback.md) remain useful detailed sources.
This master proposal broadens their scope, including generic processing,
shared assets, and tuning dependencies. Reconcile the relevant documents and
remove superseded restrictions when implementing those changes; this task
does not silently rewrite their existing specifications.

An older `plan/editing-tools.md` appeared in project history, but is absent from
the inspected tree. Use the actual `recs/edit/` implementation as the current
baseline, not the historical proposal as evidence of missing functionality.
