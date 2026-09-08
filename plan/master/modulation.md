# Envelopes, LFOs, and modulation

Part of the [master proposal](master.md). Stage 3 design work, revised
8 September 2026. The existing envelope and LFO models are an inventory of
current behavior, not the final common contract. Resolve this design before
implementing a sampler or adding audio waveform generation.

## Current starting point

Recsam's `Envelope` has delay, attack, hold, decay, sustain, release, and named
segment shapes. `ModulationEnvelope` adds a local identity. `LFO` has frequency,
voice/instrument scope, waveform, delay, and initial phase. These fields do not
by themselves settle retriggering, interrupted stages, tempo changes, phase
continuity, or exact interpolation. Tuney's oscillator supplies additional
waveform and duty-cycle behavior to review in [Processors](processors.md).

The goal is a compact reusable control model for amplitude, pitch, filters,
lighting, and other quantities. A control generator produces a declared value
domain; a separate typed mapping gives that value its destination meaning.
For example, pitch ratios multiply Hz, while gain in dB requires a defined
conversion before multiplication of audio samples.

## Envelope decisions to settle

| Subject | Required decision and example |
| --- | --- |
| Shape vocabulary | Choose whether ordered segments, levels, and transitions are the common body, with ADSR as a preset; avoid independent ADSR and general-envelope engines |
| Time | Define seconds and, where needed, musical durations; specify tempo changes during a segment and conversion at a sample boundary |
| Curves | Give each retained curve an equation, parameter meaning, endpoints, and behavior for a zero target; names such as exponential are insufficient |
| Gate and release | Specify release during delay, attack, hold, decay, or sustain; state whether release starts from the current value and how its duration is measured |
| Retrigger | Decide reset, continuation, or retrigger from the current value, and how legato differs from an independent trigger |
| Sustain and loops | Define held points, optional loop entry/exit, and the effect of pedal sustain without conflating a physical key with a gate |
| Completion | Distinguish envelope completion from voice retirement, release-sample triggering, choke, and transport stop |
| Instance scope | Define state ownership per trigger/voice, logical part, or instrument; two uses of one definition must not accidentally share state |

Compare a simple ADSR, an interrupted attack, a curved decay to zero, and a
looped control contour before choosing the first profile. Retain only features
whose interactions can be specified clearly. Document intentional changes from
existing recsam behavior; backward compatibility does not require preserving
primitive or underspecified semantics.

## LFO decisions to settle

Separate waveform shape from the advancing phase and its lifecycle. Reuse a
shared shape contract with audio oscillators where the mathematics agrees,
while declaring the distinct clock, evaluation-rate, and anti-aliasing needs.

| Subject | Required decision and example |
| --- | --- |
| Rate and clock | Distinguish cycles per second from tempo-relative rates; specify phase accumulation when either frequency or tempo changes |
| Phase and reset | Choose free-running, transport-synchronized, or trigger-reset behavior; define phase units, wrap convention, and repeated triggers |
| Waveform | Define sine, pulse, triangle/saw, polarity, duty/skew, and discontinuity values precisely; review Tuney's actual orientation at duty extremes |
| Start and stop | Specify delay, fade-in/out, and whether phase advances during a delay or an inactive interval |
| Scope | Decide whether voices share phase, start independent phases, or use explicit offsets from an instrument source |
| Depth and offset | Define their units and composition with the destination's base value, other modulation, and clipping/range policy |
| Discrete/random sources | Add stepped or sample-and-hold behavior only with explicit update boundaries; portable randomness needs a named algorithm, seed, and reset rules |
| Seeking | Define reconstruction or state restoration at a requested position and behavior across transport discontinuities |

Audio-rate modulation, feedback, and stochastic sources are candidates, not
mandatory first-profile features. Avoid treating a control-rate approximation
as equivalent to an audio-rate oscillator merely because both are called LFOs.

## Connection and event semantics

Every route names its source, target parameter, value domain, scope, and
combination operation. Define the ordering of base values, authored automation,
envelopes, LFOs, and external controls where order affects the result. Reject an
ambiguous route rather than infer units or combine by connection-list accident.

Define equal-time trigger, release, pedal, parameter-change, and reset ordering.
Specify interpolation between control observations and behavior at exact
segment boundaries, including zero-duration segments. An arbitrary host block
must not change control timing or turn one-sample transitions into block steps.

## Design gate and portable evidence

Before renderer implementation, publish the selected small model, state
transitions, equations, valid/invalid documents, and expected control values
at named times. Cover interrupted release, retrigger, sustain, zero-duration
segments, phase reset, changing rate, independent instances, and different
evaluation partitions. These are event/state and scalar-control fixtures;
they do not require audio waveform generation.

Define exact comparisons for identities, ordering, and rational timing, plus
explicit tolerances for transcendental control values. A Python evaluator may
serve as a reference later, but the equations and language-neutral fixtures
must stand on their own for a compiled implementation. The deferred sampler
must consume this contract rather than establish it through incidental code.

## Additional work beyond the prompt

None.
