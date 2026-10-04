# Remaining musical-model and DSP decisions

These are unresolved extensions, not instructions to rebuild existing models.
Use [the plan index](../README.md) for owners and authoritative specifications.
Each extension needs concrete semantics and language-neutral conformance cases.

Navigation: [instruments](#sample-instruments-and-performance-objects),
[modulation](#envelopes-lfos-and-modulation),
[DSP](#synthesizers-dsp-and-analysis-graphs), [pitch](#pitch-tunings-and-scales).

## Sample instruments and performance objects

Instrument authoring, playback hosts, and plugin/VST integration remain separate
application work. They belong outside recs and uFor. Use
[enge's roadmap](../../../enge/plan/roadmap.md) for remaining engine work rather
than maintaining another synth or sampler checklist here.

If a future profile adds trigger-wide capacities beyond existing voice pools,
specify deterministic retirement and release-sample behavior explicitly. One
trigger can own several voices; trigger limits and voice limits are distinct.

## Envelopes, LFOs, and modulation

Remaining model extensions include looped envelopes, random/sample-and-hold
sources, continuous LFO rate ramps, modulation feedback, and general audio-rate
execution. A looped envelope needs entry/exit, release-from-loop, and zero-time
cycle rules. These require their own conformance cases rather than another
envelope or oscillator implementation.

Named envelope and addressed LFO event integration belongs to
[enge's execution plan](../../../enge/plan/engine-execution.md).
The current contracts are documented in
[uFor's modulation format](../../../ufor/doc/modulation-format.md).

## Synthesizers, DSP, and analysis graphs

General cross-domain processor graphs, host latency compensation, and plugin
hosting remain proposed work. enge owns its engine and effects extensions;
the following graph design is not a claim that those implementations are absent.

### Operation and instance

An operation definition specifies typed ports, parameter semantics, state
lifetime, latency behavior, and the meaning of its result. An instance supplies
an ID and parameter values. Its realization is either a graph of operations or
an installed implementation selected by a [binding](future-proposals.md#implementations-endpoints-and-parameter-mappings).

| Operation | Input | Output | Parameters that need concrete semantics |
| --- | --- | --- | --- |
| Oscillator | Optional pitch/modulation | Audio | Hz, waveform, phase/reset, amplitude, duty cycle |
| Filter | Audio, optional modulation | Audio | Response type, cutoff Hz, resonance convention, order |
| Delay | Audio | Audio | Delay seconds, feedback multiplier, wet/dry, maximum delay |
| Compressor | Audio and optional sidechain | Audio | Threshold dBFS, ratio, attack/release seconds, knee, detector mode |
| Distortion | Audio | Audio | Transfer function or named algorithm, drive, oversampling policy |
| Pitch estimator | Audio | Frequency and confidence | Observation window, hop, supported pitch range, effective timestamp |
| Envelope follower | Audio | Amplitude control | Detector and attack/release semantics |
| Mapper | Typed control | Another typed control | Explicit mathematical or tabulated transformation |

Do not assume that similarly named operations have identical DSP. An abstract
compressor describes intent; an exact operation contract additionally fixes its
detector, knee, envelope equations, channel linking, and numerical behavior.
Bind abstract intent only to a declared matching profile, and record the choice.

### Graph contract

A processor score contains `nodes`, `connections`, and exported `ports`.
Each node references exactly one operation or dependent score. Input ports
accept one producer unless their definition declares an explicit merge rule.
Audio summing uses a mixer; events use an ordered merge; lighting uses its own
compositor. Converters are visible nodes. Matching scalar types alone does not
make a connection valid.

Illustrative fragment connecting a pitch detector to a light control:

```toml
[[nodes]]
id = "pitch"
operation = "recs.pitch_estimator"
parameters = { minimum_hz = 80.0, maximum_hz = 1200.0 }

[[nodes]]
id = "color_position"
operation = "recs.log_frequency_map"
parameters = { minimum_hz = 80.0, maximum_hz = 1200.0 }

[[connections]]
source = { node = "pitch", port = "frequency" }
destination = { node = "color_position", port = "frequency" }
```

The full graph also routes audio into `pitch`, handles its confidence output,
and connects the mapper to a palette/light generator. Unvoiced input requires
an explicit behavior such as hold, fade, or no update. This example does not
authorize a hidden arbitrary conversion from audio directly to RGB.

### Feedback and latency

The general processor scheduler should first support acyclic graphs.
Ordinary delay and feedback effects
can be encapsulated operations with defined internal state; that covers many
synthesizer patches without permitting algebraic graph loops.

Exposed graph feedback is a separate capability. Every cycle must include a
stateful delay with at least one sample of delay in a declared processing
timebase. Removing those delayed edges must yield an acyclic instantaneous
dependency graph. A one-sample cycle cannot be implemented by arbitrarily
delaying an entire host block. Reject it until the scheduler can honor its
declared granularity. Event-trigger cycles require a positive scheduling delay
and a bounded event-production contract as well.

Each implementation declares processing latency, required lookahead, block-size
constraints, supported rates/layouts, and tail behavior. The host aligns parallel
audio paths when requested using explicit compensation in the prepared graph.
A live analysis delay remains real delay. Cross-domain outputs can align to a
chosen presentation time by buffering faster paths, subject to the run's
latency budget.

### Preparation and execution

Separate pure model validation, dependency/asset resolution, implementation
preparation, bounded processing, and encoding/device delivery. Prepare lookup
tables, buffers, plugin instances, and parameter maps before starting a run.
The common model must not require filesystem or network I/O during rendering.

The same prepared semantics serve offline and real-time hosts. The real-time
host owns clock deadlines and output queues. The offline host requests bounded
blocks for a finite interval. A node declares whether it can run offline, needs
a live endpoint, can seek, can save/restore state, and has deterministic output
given state and inputs. Missing live dependencies prevent a complete offline
render unless the score explicitly supplies replacement material.

Run records pin implementations and state assets where supported. Capturing a
processor's output is the reliable way to retain an otherwise unavailable or
nonreproducible realization. Plugin version identifiers alone cannot guarantee
sample-identical results on every machine.

## Pitch, tunings, and scales

Remaining work includes noncontiguous tuning maps, broader keyboard mappings,
MTS byte import and sparse updates, and their host realization policies. Existing
pitch expressions, dense finite/repeating tables, scale calculations, Scala
conversion, and oscillator contracts belong to uFor's documentation.

### Sparse mappings and host policy

A finite table need not be ascending or contiguous. Undefined degrees must remain
explicit during validation and preparation. An instrument's decision to
substitute a playable note belongs to a separate visible mapping policy, not
modulo indexing in the tuning definition. Do not copy tuney's instrument-range
fallback into the portable model.

Keyboard mappings and reference frequency are separate from Scala scale data.
Preserve that separation when adding keyboard-map import. Report interchange
rounding and unsupported expressions.

### MIDI tuning interchange

MIDI Tuning Standard per-key frequency tables are finite mappings and must not
gain automatic repetition. Scale/Octave extensions need explicit repetition
semantics in their adapter. Exporting a finite table to a repeating format
requires an explicit musical decision. See the
[MIDI Association's tuning specification summary](https://midi.org/midi-tuning-updated-specification).

Broader MIDI 2.0 semantic conversion, MIDI-CI host integration, SysEx
reassembly, and conversion remain separate from exact raw UMP packet storage.

### Performance mapping and acceptance

Specify whether pitch bend acts before or after retuning, with explicit scope
and range. MIDI and CV bindings must report quantization and limitations on
independent pitches. Host mapping and educational presentation must not silently
change the underlying tuning.

Extend portable fixtures for noncontiguous finite ratio/Hz tables, undefined
degrees, keyboard maps, MTS per-key tables, and sparse updates. Define numeric
tolerances for interchange rounding. Keep UI annotations, file dialogs, and
fallback selection local to the application.

## Additional work beyond the prompt

None.
