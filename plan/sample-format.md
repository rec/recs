# Remaining Recsam Format Work

## Scope

The current recsam instrument model already specifies sustain loops,
alternative selection, choke groups, layer crossfades, release and sustain
samples, articulations, named live controls, modulation envelopes, LFOs,
panning, stereo balance, and pitch bend. On 8 September 2026 the user reopened
envelopes and LFOs for deeper design before any further waveform generation.
Other existing fields remain implementation inventory, not proof of a sampler.

The sections below are unresolved additions. They require explicit approval and
format design before changing `doc/sample-format.md` or the Pydantic models.
Playback implementation remains separate in [Sample Playback](sample-playback.md).

## Envelopes And LFOs Come First

Follow the [modulation design](master/modulation.md) before implementing a
sampler or extending waveform generation. Replace the assumption that current
ADSR-like fields and a frequency/phase LFO are sufficient with an explicit
review of curves, timing, retrigger/release, scope, phase continuity, and route
composition. Consider a compact segment/state model with common presets;
settle it with examples instead of immediately adding more optional fields.

Extract Tuney's tuning/scale and oscillator definitions alongside this work.
Keep finite tuning tables distinct from repeated ratio patterns, preserve
fractional authoring, and separate oscillator shape from phase and gain.
The resulting sampler specification should remain small enough for a later
compiled implementation, with an optional Python reference and shared tests.

## Voice Limits And Retriggering

Define predictable polyphony and repeated-trigger behavior while bounding CPU
and memory use:

- instrument-wide and optional group voice limits;
- whether limits count triggers or individual layered voices;
- repeated-trigger masking and retrigger behavior;
- deterministic voice selection when a limit is reached;
- immediate, faded, or release-stage retirement;
- interactions with choke groups, sustain, release samples, and linked layers.

The format must not leave voice stealing to player-specific defaults.

## Named Slot Groups

Add one non-nested grouping level for sharing selection and sound settings
without repeating them in every slot. Define precedence and processing order
across instrument, group, and slot values.

Groups must remain distinct from alternative-selection sets, choke groups, and
articulations even when the same slots participate in several of them.

## Synchronized Microphone Layers And Routing

Represent close, room, and ambient captures that trigger together while keeping
independent gain and output routing:

- linked selection so one alternative take is chosen across all microphones;
- explicit channel selection and channel layout;
- named output destinations without implicit downmixing;
- optional alignment offsets when source files do not begin at the same frame.

The existing panning and stereo-balance fields cover spatial adjustment, not
layer synchronization or routing.

## Named Slices

Allow multiple slots to reference named half-open frame ranges in a shared audio
asset. Slice boundaries must have one authoritative declaration and use native
sample frames. Slots retain their own mapping, trigger, and processing values.

This avoids duplicating audio and avoids repeating trim boundaries throughout
an instrument.

## Reproducible Variation

Specify deterministic alternative selection and randomized parameter values:

- seed ownership and reset rules;
- the exact random-selection algorithm;
- independence from processing block size and unrelated voices;
- stable behavior for the same instrument, event stream, and initial state.

This is required before adding random delay, offset, pitch, gain, or SFZ random
region selection.

## Deferred Filter Design

Resonant filters still need a separate design covering filter types, frequency
and resonance units, modulation, composition across instrument and slot scopes,
stability, and conformance tests. Existing peaking EQ remains unchanged.

Granular playback, time stretching, arbitrary effect chains, and microtonality
remain outside this plan.

## Suggested Order

1. Envelope/LFO design and Tuney definition extraction under master stage 3.
2. A small instrument/performance contract with language-neutral examples.
3. Voice limits and retriggering where needed by that retained contract.
4. Named slices, groups, and synchronized microphone layers if retained.
5. Reproducible variation and filters as separately settled extensions.

No step above authorizes sampler waveform generation. Choose its language,
backend, and possible VST hosting only after the model gate.

## Additional Work Beyond The Prompt

None.
