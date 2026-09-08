# Sample Playback

## Status And Scope

Deferred implementation proposal, revised 8 September 2026. The user has
postponed further audio waveform generation, especially the sampler. First
settle the small portable musical model, including Tuney's tuning/scale and
oscillator extraction and a deeper envelope/LFO design. This document describes
possible execution work after that gate and a separate decision to resume.
It does not select Python, a compiled language, or a plugin SDK.

Related documents:

- [Master roadmap](master/how-to.md): stage 3 model work and deferred execution.
- [Tunings and scales](master/tunings.md): finite/repeating domains and the
  frequency/ratio minilanguage.
- [Envelopes and LFOs](master/modulation.md): required design before playback.
- [Recsam Instrument Format](../doc/sample-format.md): implemented TOML schema
  and Pydantic models.
- [Remaining Recsam Format Work](sample-format.md): candidate features awaiting
  review.
- `recs/edit/`: the existing session-to-session editing framework.

Recs already has recording, MIDI capture, audio-file I/O, session records, and
materialized session-to-session edits. Sample playback still needs a new
stateful audio engine; it is not simply another recording source or a
collection of independent edit commands.

Microtonality belongs to the shared tuning and performance contract. Current
format and event models exist; they do not constitute a sampler implementation.

## Separate Creation From Playback

### Instrument Creation

The following audio-producing workflow is deferred too. Model work may define
assets and slices referring to existing samples without generating new audio.

An audio edit creates a playable instrument definition:

1. Read selected recordings from an input session record.
2. Extract sample material or define slices, assign key and normalized velocity ranges,
   and attach playback settings and tags.
3. Write a new session directory containing generated audio,
   `sample-instrument.toml`, the session record, and the resolved edit definition
   required by the editing plan.

Instrument references point to audio inside the new directory. Slices may share one
generated audio file rather than duplicate it. The resulting instrument does not
require the original recording session for playback.

Loops, articulations, and named-control behavior remain instructions for the
player. They are not permanently baked into the sample files. Unsupported
input media is omitted according to the editing plan's media-selection rules.

### Instrument Playback

A later player combines an instrument with timed performance events to produce
audio. After execution resumes, offline evaluation can establish behavior
before a live host is added. The core consumes the shared trigger, release,
and control contract, with MIDI, OSC, and sequencers as adapters. Python is
not required for that core or for its first implementation.

## Proposed Sampler Subsystem

The current instrument models live in `recs/recsam/`. Design a small sampler
contract separate from document parsing, host wrappers, and recording machinery.
Do not create `recs/sampler/` as an assumed Python implementation yet. The
names below describe responsibilities, not mandatory Python runtime classes:

| Class | Responsibility |
| --- | --- |
| `SampleInstrument`, `Instrument`, `SampleSlot` | Existing recsam Pydantic models for the document, shared settings, and slots |
| `Trigger`, `Release`, `ControlChange` | Existing frame-timed recsam event models with logical parts and trigger IDs |
| `PreparedInstrument` | Validated assets, resolved settings, and efficient key/velocity lookup |
| `PerformanceState` | Named controls per scope, trigger ownership, sustain, articulations, alternate-take counters, and random state |
| `Voice` | Playback position, direction, loop state, envelope, and filter state |
| `Sampler` | Consume timed events, manage voices, and render audio blocks |

Separate immutable instrument definitions from mutable performance and voice state.
Resolve TOML, validation, and inherited settings before rendering rather than
repeating that work inside the audio loop.

Use composition, not a subclass for every feature. The candidate features fall
into four areas:

- Slot selection: layers, alternate takes, and articulations.
- Voice lifecycle: release samples, pedals, choke groups, and polyphony.
- Audio processing: direction, loops, envelopes, EQ, modulation, and crossfades.
- Organization: groups, named slices, microphone links, and routing.

Only implement retained features after their defaults and interactions are
specified. For example, selection, choking, and layering cannot independently
make conflicting decisions about voices created by the same event.

## One Engine, Two Hosts

The core consumes events at integer output-frame positions and renders bounded
audio blocks. It has no dependency on audio devices, session-record writing, or
the file-output policy. Asset loading is handled outside its rendering loop.

Use the implemented `ufor.events.PerformanceEvent` contract. Preserve native
ticks and ordinals until the host resolves the engine's execution clock. Validate control
names and values against the loaded instrument;
the engine additionally owns trigger-ID lifetime and release matching. Selection
keys do not imply pitch. Hosts supply target frequencies for pitch-tracked
samples, whose mappings declare reference frequencies.

Transport adapters normalize input into unipolar or bipolar floating-point
controls without reducing precision to seven bits. MIDI-specific channel and
controller numbers, zero-velocity note-on conversion, repeated-note matching,
and MPE assignments remain in the MIDI adapter. OSC addresses remain in its
adapter. The engine treats zero-velocity Trigger events as genuine triggers.

### Deferred Offline Host

The offline host reads recorded MIDI and the instrument, converts messages
through its adapter, schedules performance events, drives the engine, and writes
the resulting audio as a new Recs output session.

Convert MIDI timing, including tempo changes, into output-frame positions
before scheduling. Split render blocks at event boundaries so triggers and
control changes are not quantized to the beginning of a block. Preserve a
defined order for events at the same frame.

The host owns session creation, output encoding, provenance, and file lifecycle
entries. The sampler only supplies audio. Offline rendering provides a
deterministic environment for establishing behavior and regression tests before
taking on live latency.

### Live Host Later

The live host adapts and timestamps incoming performance input, schedules it
against the output audio clock, and drives the same sampler through an audio
output stream. MIDI is one adapter, not a required engine input.

Do not put file access, decoding, blocking operations, or configuration parsing
in the audio callback. Prepare assets and buffers outside that callback. See
the [Sounddevice callback requirements](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html).

Live playback is a separate host, not a reason to couple the sampler to the
recording daemon. Device latency, event scheduling, and underrun behavior need
their own validation after offline correctness is established.

## Reuse Existing Recs Components

Recs's host can reuse its common document readers, recording finalizer, command
models, and application logging. Pydantic, Tyro, NumPy arrays, and Python file
I/O belong to that implementation boundary, not the portable sampler contract.
An optional Python reference may use existing audio dependencies when rendering
resumes. A compiled core must not need to import the Recs application.

Do not subclass `SourceRecorder` or route rendered output through
`ChannelWriter`. Those classes carry device-recording, silence-detection, and
segmentation policies that do not belong in sample playback. An offline render
must preserve its requested timeline rather than inherit recording decisions
about quiet material.

The editor and sampler should share DSP primitives when both actually
need them. Do not build a general-purpose processing framework in advance or
force unrelated recording classes to serve as sampler abstractions.

## DSP Backend And Resource Use

Do not select a backend before the envelope/LFO and instrument contracts are
small and concrete. Compare these later implementation choices:

| Choice | Tradeoff to evaluate |
| --- | --- |
| Compiled core directly | A small language-neutral spec and conformance suite can avoid implementing the whole sampler twice |
| Python reference, then compiled port | Easier exploration of state and numerical behavior, but two implementations must be maintained against shared tests |
| Existing engine behind a binding | Saves engine work only if the retained musical and timing semantics can be represented without silent changes |

A VST instrument is a possible wrapper around the core. Keep plugin parameters,
host event translation, state persistence, and lifecycle separate from the
musical model. Evaluate SDK, language, platform, and packaging requirements at
that later decision; no new project or dependency is selected here.

The current dependencies are not a complete sampler engine. Select a playback
engine only after completing the sampler backend checks in
[Human And Experimental Verification](human.md). Translating the format to
another engine's input syntax must not silently change retained TOML semantics.

If no complete engine fits, reuse suitable DSP libraries for the expensive
primitives while keeping Recs' selection and lifecycle rules explicit. Backend
and dependency choices require evaluation before implementation; this proposal
does not select or add a dependency.

Share decoded sample data between voices. Each voice owns its playback and DSP
state, not a private copy of the sample. Bound rendering buffers and define a
cache budget for large instruments. Do not assume that loading every recording into
memory is acceptable.

If a Python reference is chosen, avoid Python loops over individual samples
for expensive DSP. That consideration does not determine the core's language.

## Shared Conformance Before Two Implementations

Publish language-neutral documents, event streams, initial state, expected
state transitions, and scalar pitch/control values before building a renderer.
Include finite-table boundaries, periodic ratios, exact fractions, oscillator
phase conventions, envelope interruption, LFO reset, and voice independence.
Specify numeric precision and tolerances, ordering at equal times, and units.

After the audio-generation pause ends, add identical asset/event fixtures for
each implementation. Compare rendered output across block sizes, rates, and
implementations using explicit tolerances; do not promise bit identity across
different floating-point math libraries unless the contract requires it.
Run the shared suite in each implementation's CI. Fix the specification or an
incorrect implementation when they disagree instead of retaining divergent
Python and compiled expectations. VST host behavior needs separate later tests.

## Suggested Implementation Order

1. Complete master stage 3: tuning/scale and oscillator definitions, the
   frequency/ratio language, and the envelope/LFO redesign.
2. Trim the instrument and sampler contract; resolve retained interactions and
   publish language-neutral document, pitch, control, and state fixtures.
3. Stop at the model gate. Decide separately when to resume audio generation
   and whether to use a compiled core, Python reference/port, or existing engine.
4. After that decision, implement asset preparation and bounded rendering with
   the shared event contract and an offline host. Preserve trigger identity,
   pitch separation, and control precision.
5. Establish audio conformance across block sizes and any reference/compiled
   implementations. Check retirement, shared-asset memory use, and modulation.
6. Add live or VST hosting only with explicit lifecycle and timing contracts,
   reusing the same core rather than adding a different sampler per host.

When audio generation resumes, follow Recs' existing 48 kHz,
at-least-one-second WAV convention for digital audio regression fixtures.
Test rendered output and visible behavior rather
than private implementation details. Hardware acceptance is defined in
[Human And Experimental Verification](human.md).

## Additional Work Beyond The Prompt

None.
