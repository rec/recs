# Synthesizers, DSP, and analysis graphs

Part of the [master proposal](master.md). Sources generate data, processors
transform it, and sinks consume it. These are roles determined by ports, not
three unrelated class hierarchies.

## Operation and instance

An operation definition specifies typed ports, parameter semantics, state
lifetime, latency behavior, and the meaning of its result. An instance supplies
an ID and parameter values. Its realization is either a graph of operations or
an installed implementation selected by a [binding](bindings.md).

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

## Graph contract

A processor document contains `nodes`, `connections`, and exported `ports`.
Each node references exactly one operation or dependent document. Input ports
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

## Feedback and latency

The first scheduler supports acyclic graphs. Ordinary delay and feedback effects
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

## Preparation and execution

Separate pure model validation, dependency/asset resolution, implementation
preparation, bounded processing, and encoding/device delivery. Prepare lookup
tables, buffers, plugin instances, and parameter maps before starting a run.
The common model must not require filesystem or network I/O during rendering.

The same prepared semantics serve offline and real-time hosts. The real-time
host owns clock deadlines and output queues. The offline host requests bounded
blocks for a finite interval. A node declares whether it can run offline, needs
a live endpoint, can seek, can save/restore state, and has deterministic output
given state and inputs. Missing live dependencies prevent a complete offline
render unless the document explicitly supplies replacement material.

Run records pin implementations and state assets where supported. Capturing a
processor's output is the reliable way to retain an otherwise unavailable or
nonreproducible realization. Plugin version identifiers alone cannot guarantee
sample-identical results on every machine.

## Change from today

Reuse Recs's existing separation of graph validation, materialized audio,
rendering, and output encoding. Generalize port types and processing nodes
instead of adding parallel renderers to each CLI edit command. Keep recsam
voice rendering as a specialized engine behind its common ports.

Lyte's `AnimationSpec`/`MixerSpec` already describe source graphs, but `impl`
currently resolves Python factories. Move that executable lookup to installed
bindings. Tuney's `Oscillator` currently combines waveform selection and runtime
generation; expose its algorithm through a synthesis definition while leaving
its tuning UI local. No new DSP engine or plugin host is implemented by this
documentation change.
