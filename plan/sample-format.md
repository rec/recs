# Sample Format Work

## Scope

The current uFor sample-instrument model specifies sustain loops,
alternative selection, choke groups, layer crossfades, release and sustain
samples, articulations, named live controls, modulation envelopes, LFOs,
panning, stereo balance, and pitch bend. The 8 September 2026 model-first pause
is historical: an initial modulation profile, synth definition, and both
instrument traces now exist. enge owns synth and sampler realization. Existing
format fields are not proof that every feature has engine support.

The Recsam type extraction, named slices, explicit channel maps, richer
envelopes/LFOs, SFZ cutover, voice policy, deterministic preparation trace, and
reproducible selection and variation are implemented in uFor. SFZ `lorand` and
`hirand` map to portable random-range conditions; engine-dependent random
parameter opcodes remain diagnosed as unsupported.

Playback implementation remains separate in [Sample Playback](sample-playback.md).
Any further sample-format addition requires explicit approval and format design.

## Modulation profile and further extensions

The initial [modulation design](master/deferred-work.md#envelopes-lfos-and-modulation)
is implemented. Further curves, timing, retrigger/release behavior, scope, phase
continuity, and route composition need explicit semantics and fixtures before
new fields or engine support are added.

The initial tuney tuning/scale and oscillator extraction is complete.
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

Implemented in uFor. Slots reference named half-open native-frame ranges in
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
