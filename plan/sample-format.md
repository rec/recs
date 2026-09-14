# Sample Format Work

## Scope

The current Ufor sample-instrument model specifies sustain loops,
alternative selection, choke groups, layer crossfades, release and sustain
samples, articulations, named live controls, modulation envelopes, LFOs,
panning, stereo balance, and pitch bend. On 8 September 2026 the user reopened
envelopes and LFOs for deeper design before any further waveform generation.
Other existing fields remain implementation inventory, not proof of a sampler.

The Recsam type extraction, named slices, explicit channel maps, richer
envelopes/LFOs, SFZ cutover, voice policy, deterministic preparation trace, and
reproducible selection and variation are implemented in Ufor. SFZ `lorand` and
`hirand` map to portable random-range conditions; engine-dependent random
parameter opcodes remain diagnosed as unsupported.

Playback implementation remains separate in [Sample Playback](sample-playback.md).
Any further sample-format addition requires explicit approval and format design.

## Envelopes And LFOs Come First

Follow the [modulation design](master/deferred-work.md#envelopes-lfos-and-modulation) before implementing a
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

Implemented: instrument-wide limits count individual layered voices. Same-key and
overflow policies retire selected voices deterministically, and their interaction
with sustain, release samples, choking, and linked layers is pinned by semantic
trace conformance tests.

## Named Slices

Implemented in Ufor. Slots reference named half-open native-frame ranges in
sealed audio assets, with contained loop ranges. There is no duplicated sample
path or trim interval on each slot. Linked microphone take selection is
implemented.

## Reproducible Variation

Implemented: named selection sets, delay, offset, pitch, gain variation, and
portable random-range eligibility each have explicit seeded algorithms that are
independent of audio block size and unrelated voices. Random ranges preserve SFZ
source intervals, including overlaps and gaps, rather than collapsing them into
equal-choice selection.

Granular playback, time stretching, arbitrary effect chains, and microtonality
remain outside this plan.

## Next Decision

Sample-format work is complete. Before any renderer or backend choice, add the
sibling synth-instrument definition and the shared offline lifecycle contract
described in [Sample Playback](sample-playback.md). Waveform generation still
requires a later explicit decision on language, backend, and possible host.

## Additional Work Beyond The Prompt

None.
