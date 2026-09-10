# Sample instruments and performance objects

Part of the [master proposal](master.md). An instrument consumes performance
events and produces named streams. A sample instrument is one realization;
a synthesizer graph can expose the same performance interface.

Revision, 8 September 2026: stage 3 extracts and improves definitions and
performance semantics. Sampler implementation and further waveform generation
are deferred. The first [envelope and LFO profile](modulation.md) is now
implemented in Ufor. The [instrument contract](../../../ufor/doc/instrument-format.md)
now implements the native root, sealed assets, named slices, channel maps,
source bindings, shared performance events and typed routes. Pure SFZ conversion
and every portable Recsam model now live in Ufor. Preparation and performance
action traces remain; no sampler language has been selected.

## Preserve the useful recsam model

The [Ufor sample format](../../../ufor/doc/instrument-format.md) and
`ufor/samples/` models describe slots, key/velocity selection, loops,
articulations, sustain, choke groups, crossfades, envelopes, LFOs, scoped
controls, EQ, and independent reference pitch. Keep those musical concepts.
Do not flatten them into thousands of primitive graph connections simply to
make every object look identical.

The new instrument document wraps a typed `sample_instrument` definition,
exposes a performance input and named audio outputs, and references common
assets, parameters, and events. General processing after the instrument uses
the processor graph. Voice-specific processing stays in its voice template.

## Assets and slots

Replace `SampleSlot.sample` paths with asset IDs. Asset metadata owns native
sample rate, frame count, channel layout, and encoding. A named slice owns one
half-open range in that asset's native frames; slots reference that slice.
Loop positions stay in the same native asset frame coordinates and must be
contained in the selected slice. Never express sample trim points in musical
beats or reinterpret them at the output sample rate.

A slot selects keys and velocity intervals, trigger kind, articulation, and
optional alternate-take set. Key is a selection coordinate; target pitch is
independent. A pitch-tracked slot declares `reference_pitch_hz` and requires a
resolved performance pitch. Unpitched percussion does not need a fictitious
reference pitch.

Slot playback uses nullable overrides: omission inherits, while an explicit
default overrides. Envelope overrides replace the complete envelope.
Preparation resolves these declarations into complete immutable voice settings.
Do not replace every combination rule with a generic dictionary merge:
additive gain in dB, envelope overrides, and local modulation references have
different existing meanings. Preserve them explicitly during the first cutover.

The Ufor envelope/LFO profile intentionally changes some current rules.
Its [cutover table](../../../ufor/doc/modulation-format.md#changes-from-recsam-and-remaining-boundaries)
specifies segment expansion, curve translation, exact timing, retriggering,
and phase during delay. Resolve inheritance into a complete envelope before
constructing its Ufor definition; do not layer partial segment lists through
a generic merge.

## Voice and layer behavior

One performance trigger may create several voices. Distinguish a trigger limit
from a voice limit. Before playback implementation, define both capacities and
deterministic retirement: released voices first, then oldest trigger, with ID
as a tie-breaker. Retirement applies the instrument's explicit fade duration.
It must not depend on processing block size or incidental container order.

Sustain retains the existing pedal and release-trigger semantics. Choking a
group, releasing a key, stealing a voice, and stopping transport are distinct
causes of retirement. Define which causes fire release samples; do not let an
implementation accidentally emit a release sample for every internal removal.

For multiple microphones, add linked layers only with a shared take-selection
identity. Choose the take once, then create close/room voices from that same
take, each with explicit channel selection, alignment offset, gain, and output.
Independent microphone random selection would create a performance that was
never recorded.

Round-robin counters belong to named selection sets and reset at the declared
performance start. Random behavior requires an identified algorithm and seed,
plus reset rules independent of block size. The first usable profile may use
deterministic ordered selection only; stochastic portability is a later feature
until its algorithm has conformance examples.

## Processing and reuse

An instrument can expose `dry`, `room`, or other named outputs. A parent
arrangement connects those explicitly. Each instrument node instance owns its
voice/control state; two uses of the same definition do not share sustain or
round-robin counters. Both slot and instrument processing run per voice before
mixing, preserving the original sample contract. A shared post-mix/send effect
is a separate graph node.

Keep normalized performance controls independent of MIDI CC numbers and OSC
addresses. One named `breath` control can shape a sample filter, an oscillator,
and light intensity through explicit mappings, without teaching the sampler
those transport protocols.

## Small sampler contract and later implementations

First define a bounded contract for asset slices, prepared instrument settings,
performance events, voice state, and the modulation model. Keep authoring and
host concerns outside that core. Publish event/state examples without rendering
audio; do not let a Python-specific class layout become the portable contract.

A later implementation decision should compare a compiled core, an optional
Python reference followed by a compiled port, and reuse of a suitable existing
engine. A VST instrument is a possible host wrapper for the core, not the
instrument document format. No language, plugin SDK, or Python-first engine is
selected by this plan revision. See [Sample Playback](../sample-playback.md)
for the deferred implementation and shared conformance requirements.

## External samplers and change from today

`InstrumentScore` is now the common root; `SampleInstrument` is its typed
body. The former `format_version` root and Recsam model modules are removed.
`ufor.sfz` owns pure conversion with explicit unsupported-feature diagnostics.
Recs retains local path resolution, symlink containment, hashing, decoding and
embedded-loop inspection. There is no parallel native format.

Existing `Processing` and `SoundSettings` represent a limited sound-processing
vocabulary. General DSP belongs in [Processors](processors.md); the existing
peaking EQ does not already implement arbitrary filters or synthesis. The
[playback plan](../sample-playback.md) still describes an engine to build.
Adopting a universal envelope does not make that stateful engine exist.

## Additional work beyond the prompt

None.
