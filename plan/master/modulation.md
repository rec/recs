# Envelopes, LFOs, and modulation

## Incomplete

Instrument preparation, pedal and legato gate delivery, voice retirement,
portable action traces, oscillator lifecycle integration, loops, random
sources, continuous rate ramps, feedback, and audio-rate execution remain
unfinished. Sampler and VST work remain separate deferred execution decisions.

## Completed

Stage 3, step 4 now has an implemented first control profile in Ufor. The
canonical [modulation specification](../../../ufor/doc/modulation-format.md)
contains the equations, state transitions, ownership, mapping rules, examples,
and explicit changes from Recsam. Its
[portable cases](../../../ufor/conformance/modulation.json) run against pure
scalar reference calculations. No audio waveform buffers or sampler engine
are produced.

## Selected model

| Subject | First-profile decision |
| --- | --- |
| Envelope shape | One ordered segment representation, with a separate release list; ADSR is an authoring preset |
| Curves | Normalized exponential with signed curvature; zero is linear, and +/-5 reproduces Recsam's documented exponential directions |
| Time | Exact rational seconds or quarter-note beats; hosts supply integrated beat position; no per-stage frame rounding |
| Release | Capture the current level, skip remaining on-segments, consume the full release duration; repeated releases do not restart |
| Retrigger | Explicit current-value, reset-to-initial, or ignore policy |
| Sustain | Hold the final on-list level; physical pedal and legato decisions remain in the instrument adapter |
| Completion | Hold the terminal level and report completion; voice retirement is separate |
| LFO phase | Exact rational phase with continuous accumulation across stepped rate changes; zero rate freezes |
| LFO reset | Free, trigger-reset, or transport-reset policy; explicit reset always applies |
| Shapes | Tuney's sine, square, and duty/skew triangle equations with exact transition conventions |
| Activation | Phase advances during delay; separate activation weight preserves neutral routes and supports fade-in |
| Ownership | State per voice or per instrument instance, never shared through definition identity |
| Ordering | Strict time/ordinal order; completed and zero-time segments are consumed before each event |
| Seeking | Replay events, optionally from state bound to the same definition/history; reject backward queries from a later state |

An envelope can be unipolar or bipolar, held or one-shot, and have any finite
number of segments. A release can contain several segments and end at a
nonzero level. This supports reusable controls for pitch, filters, lighting,
and gain without imposing sample-voice policy on the definition.

## Connection contract

Sources produce dimensionless values. Routes explicitly map them into target
units or dimensionless multipliers. Source activation is applied after mapping,
interpolating from zero for addition or one for multiplication. Resolve the
base value and single replacement-automation producer, add mapped offsets,
then multiply mapped factors. Reject out-of-domain values unless an explicit
clipping operation is present. Use stable route identities for numerical
reduction, never list order as modulation priority.

These semantics are now implemented by `ufor.modulation.Modulation`, with typed
parameter domains, scope and unit checks, explicit mappings, and scalar
evaluation. See [routes](../../../ufor/doc/instrument-format.md#modulation-routes)
and [portable cases](../../../ufor/conformance/routes.json). Binding source
declarations to instrument generators and context ownership is part of the
completed native instrument cutover; the existing arrangement-only parameter target
remains separate.

## Cutover and remaining work

Recsam now uses the shared Ufor envelope/LFO definitions. The old fixed classes
and route hierarchy are removed. Native slot envelopes are whole overrides,
playback inheritance survives serialization, and SFZ adapters report unsupported
curves and behavior explicitly. There is no alternate Recsam reader.

The canonical specification gives before/after mappings, including the old
exponential curves and the changed phase behavior during LFO delay. The next
step is [instrument preparation](instruments.md), including pedal/legato
gate delivery, voice retirement, and portable action traces for these models.
Audio oscillator lifecycle integration must also use the phase/reset contract
without copying a waveform engine into Ufor.

Looped envelopes, random/sample-and-hold sources, continuous LFO rate ramps,
modulation feedback, and audio-rate execution remain deferred. A looped contour
needs explicit entry/exit and zero-time-cycle semantics; the current profile
rejects it. The sampler, compiled engine, and possible VST still require the
separate execution decision after the instrument model gate.

## Additional work beyond the prompt

None.
