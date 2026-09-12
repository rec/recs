# Deferred work

## Sample instruments and performance objects

### Incomplete

Prepared settings and performance action traces, including pedal/legato gate
delivery and voice retirement, remain to be specified. Sampler rendering,
further waveform generation, engine selection, and a VST wrapper remain
deferred.

### Preserve the useful recsam model

The [Ufor sample format](../../../ufor/doc/instrument-format.md) and
`ufor/samples/` models describe slots, key/velocity selection, loops,
articulations, sustain, choke groups, crossfades, envelopes, LFOs, scoped
controls, EQ, and independent reference pitch. Keep those musical concepts.
Do not flatten them into thousands of primitive graph connections simply to
make every object look identical.

The new instrument score wraps a typed `sample_instrument` definition,
exposes a performance input and named audio outputs, and references common
assets, parameters, and events. General processing after the instrument uses
the processor graph. Voice-specific processing stays in its voice template.

### Assets and slots

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

### Voice and layer behavior

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

### Processing and reuse

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

### Small sampler contract and later implementations

First define a bounded contract for asset slices, prepared instrument settings,
performance events, voice state, and the modulation model. Keep authoring and
host concerns outside that core. Publish event/state examples without rendering
audio; do not let a Python-specific class layout become the portable contract.

A later implementation decision should compare a compiled core, an optional
Python reference followed by a compiled port, and reuse of a suitable existing
engine. A VST instrument is a possible host wrapper for the core, not the
instrument score format. No language, plugin SDK, or Python-first engine is
selected by this plan revision. See [Sample Playback](../sample-playback.md)
for the deferred implementation and shared conformance requirements.

### External samplers and change from today

`InstrumentScore` is now the common root; `SampleInstrument` is its typed
body. The former `format_version` root and Recsam model modules are removed.
`ufor.sfz` owns pure conversion with explicit unsupported-feature diagnostics.
Recs retains local path resolution, symlink containment, hashing, decoding and
embedded-loop inspection. There is no parallel native format.

Existing `Processing` and `SoundSettings` represent a limited sound-processing
vocabulary. General DSP belongs in [Processors](deferred-work.md#synthesizers-dsp-and-analysis-graphs); the existing
peaking EQ does not already implement arbitrary filters or synthesis. The
[playback plan](../sample-playback.md) still describes an engine to build.
Adopting a universal envelope does not make that stateful engine exist.

### Additional work beyond the prompt

None.


## Envelopes, LFOs, and modulation

### Incomplete

Instrument preparation, pedal and legato gate delivery, voice retirement,
portable action traces, oscillator lifecycle integration, loops, random
sources, continuous rate ramps, feedback, and audio-rate execution remain
unfinished. Sampler and VST work remain separate deferred execution decisions.

### Selected model

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

### Connection contract

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

### Cutover and remaining work

Recsam now uses the shared Ufor envelope/LFO definitions. The old fixed classes
and route hierarchy are removed. Native slot envelopes are whole overrides,
playback inheritance survives serialization, and SFZ adapters report unsupported
curves and behavior explicitly. There is no alternate Recsam reader.

The canonical specification gives before/after mappings, including the old
exponential curves and the changed phase behavior during LFO delay. The next
step is [instrument preparation](deferred-work.md#sample-instruments-and-performance-objects), including pedal/legato
gate delivery, voice retirement, and portable action traces for these models.
Audio oscillator lifecycle integration must also use the phase/reset contract
without copying a waveform engine into Ufor.

Looped envelopes, random/sample-and-hold sources, continuous LFO rate ramps,
modulation feedback, and audio-rate execution remain deferred. A looped contour
needs explicit entry/exit and zero-time-cycle semantics; the current profile
rejects it. The sampler, compiled engine, and possible VST still require the
separate execution decision after the instrument model gate.

### Additional work beyond the prompt

None.


## Synthesizers, DSP, and analysis graphs

### Incomplete

Oscillator lifecycle integration, processor execution, graph preparation,
latency handling in a host, plugin hosting, and all new audio generation remain
deferred. The extracted oscillator definitions and scalar LFO semantics are
the completed model foundation.

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

### Extract Tuney's oscillator contract

Use `tuney/audio/oscillator.py` and its existing waveform functions as the
starting implementation evidence. Extract the definition and pure mathematical
contract from UI annotations, callable enum members, NumPy buffer allocation,
and application note handling. Plan reuse of the existing implementation when
execution work resumes; do not build a second oscillator during model work.

| Existing feature | Shared-model treatment |
| --- | --- |
| Sine | State its phase convention and output range; duty cycle has no effect |
| Square | Define pulse width, polarity, exact transition values, and behavior at duty 0 and 1 |
| Triangle/saw family | Preserve continuous duty/skew semantics and define rising/falling orientation from the actual equations, not just waveform names |
| Start, length, and period | Replace implicit sample-index conventions with an explicit phase/clock contract; settle reset and phase continuity under changing frequency |
| Key-scaled gain | Keep reference selection key and dB-per-key-interval mapping separate from oscillator Hz and waveform shape |

Tuney's gain calculation currently uses twelve key steps per scaling interval.
Do not reinterpret that as a frequency octave under an arbitrary tuning without
an explicit decision. Its square and saw/triangle implementations are not
band-limited; a future anti-aliased realization must declare the chosen profile
and tolerances rather than claim identical sample values.

Publish units, defaults, admissible values, equations, and state transitions.
Keep phase evolution separate from shape evaluation so envelopes, LFOs, and
audio oscillators can share suitable definitions without conflating their rates
or lifetime. Reconcile these decisions with [Modulation](deferred-work.md#envelopes-lfos-and-modulation).
Stage 3 acceptance uses scores, parameter mappings, phase/state examples,
and existing source inspection. New waveform generation and audio regression
fixtures wait for the later execution milestone.

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

When execution resumes, the first scheduler should support acyclic graphs.
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

### Change from today

Reuse Recs's existing separation of graph validation, materialized audio,
rendering, and output encoding. Generalize port types and processing nodes
instead of adding parallel renderers to each CLI edit command. Keep recsam
voice rendering as a planned specialized engine behind its common ports.

Lyte's `AnimationSpec`/`MixerSpec` already describe source graphs, but `impl`
currently resolves Python factories. Move that executable lookup to installed
bindings. Tuney's `Oscillator` currently combines waveform selection and runtime
generation; extract its specification and plan reuse of its implementation,
while leaving its tuning UI local. A compiled engine and VST instrument wrapper
are later options. Keep any Python reference, compiled realization, and host
wrapper accountable to the same language-neutral cases. No new DSP engine or
plugin host is implemented by this documentation change.


## Pitch, tunings, and scales

### Incomplete

Noncontiguous tuning maps, broader keyboard mappings, MTS byte import and
sparse updates, plus host realization rules, remain future model or adapter
work. The current portable model deliberately does not inherit Tuney's
instrument-range fallback.

### Repetition is musical data

Support both repeating and finite definitions, including finite frequency
ratios relative to a reference frequency. Do not infer repetition merely because
values form a list, or because an instrument must respond to every input key.

| Definition | Meaning outside the listed range |
| --- | --- |
| Repeating adjacent-ratio pattern | Continue multiplying successive intervals, including inverse traversal below the reference degree |
| Repeating reference-ratio cycle | Repeat degree ratios with an explicit frequency multiplier for each cycle |
| Finite ratio table | Only declared degrees exist; each ratio is relative to the declared reference Hz |
| Finite frequency table | Only declared degrees exist, with explicit positive Hz values |

These are distinct semantics to capture in a compact discriminated model during
stage 3. Adjacent ratios describe successive intervals; reference ratios describe
positions relative to an origin. A reader must never guess which a list means.
The earlier equal-division representation can be authoring shorthand for a
repeated single interval rather than another independently maintained model.

Separate **pattern length in steps** from **frequency multiplier per cycle**.
Western 12-tone equal temperament has a one-step repeating interval
`2^(1/12)`. Its one-step multiplier is also `2^(1/12)`; twelve steps give `2`.
A twelve-step just-intonation pattern may have twelve adjacent ratios
whose product is `2`. Neither pattern length nor multiplier is necessarily 12
or an octave. Do not force all just-intonation scales to have twelve steps.

For adjacent ratios `r[0] ... r[N-1]`, define
`f(k+1) / f(k) = r[k mod N]` relative to the reference degree. The cycle
multiplier is the product of those ratios, not a second independently editable
value. For reference ratios `q[i]` and cycle multiplier `P`, define
`f(a*N+i) = reference_hz * P^a * q[i]`, with `0 <= i < N`, `q[0] = 1`,
and degree zero at the reference. Specify Euclidean division for negative
degrees so implementations in different languages agree.

Illustrative finite ratio entries, with no wrapping:

```toml
representation = "ratio_table"
reference_hz = "440"
entries = [
  { degree = -1, ratio = "2/3" },
  { degree = 0, ratio = "1" },
  { degree = 1, ratio = "5/4" },
]
```

Degree 1 is 550 Hz; degree 2 is undefined. Frequency and ratio values are
positive, but a ratio below one is valid. A finite table need not be ascending
or contiguous. Undefined pitch remains explicit during validation/preparation.
Any instrument decision to substitute a playable note belongs to a separate,
visible mapping policy, not to modulo indexing in the tuning definition.

### Human-readable frequency and ratio expressions

Adopt the user's frequency/ratio minilanguage, a superset of Scala pitch-value
notation. Fractional authoring such as `5/4` and `2/3` is a requirement, not an
optional display convenience. `/` means division and `^` means exponentiation.
Keep exact rational arithmetic where possible; retain powers such as the
equal-tempered interval symbolically until numerical evaluation is needed.
Do not require composers to replace fractions with decimal approximations or
numerator/denominator object syntax.

TOML expression values are quoted strings. Frequency fields supply the Hz
context; ratio fields supply a dimensionless context; Scala cents values must
keep their cents meaning. A cents offset has ratio `2^(cents/1200)` regardless
of tuning step size. Parsing yields typed values or expression nodes, not
executable Python. The authored expression is authoritative; numerical results
are derived values with a stated evaluation precision.

Before implementing the parser, document the actual minilanguage's complete
grammar, precedence, associativity, grouping, signs, whitespace, and decimal
rules. `2^(1/12)` above makes the intended grouping explicit. In particular,
distinguish Scala's decimal-cents syntax from a decimal ratio or Hz value by
the declared value kind/import context. Preserve Scala inputs' meaning rather
than treating their decimals as ordinary ratios. Publish accepted and rejected
examples, zero-denominator handling, and positive finite-result requirements.
Do not invent unspecified operators while extracting the existing language.

Tuney's currently inspected `scale/evaluate.py` uses Python AST arithmetic and
math/random calls. It is not evidence that the requested `/` and `^` language
is already implemented there. Locate and reconcile the user's minilanguage
before porting a parser; Python `^` must not acquire XOR semantics. The portable
frequency language does not inherit arbitrary functions, randomness, or Python
evaluation from Tuney's broader expression UI.

### Scala and MIDI interchange

Scala is a primary tuning interchange target. Preserve its ratio/cents entries,
implicit unison, and final period entry, translating to explicit repeat
semantics. A Scala list contains offsets from unison, not adjacent interval
ratios; converting to adjacent ratios requires successive quotients. Keyboard
mapping and reference frequency are separate from that scale data. See the
[Scala scale-file specification](https://huygens-fokker.org/scala/scl_format.html).

MIDI Tuning Standard per-key frequency tables are finite mappings and must not
gain automatic repetition. The MTS Scale/Octave extensions also support
repetition; handle that explicitly in their adapter rather than assuming all
MTS messages describe the same kind of tuning. See the
[MIDI Association's tuning specification summary](https://midi.org/midi-tuning-updated-specification).
Report interchange rounding and unsupported expressions. Exporting a finite
table to a repeating format requires an explicit musical decision.

### Scales and performance

A scale selects and names degrees from a tuning. Preserve Tuney's selection,
spelling, accidentals, offsets, reference frequency, and detuning semantics.
Keyboard mappings and educational presentation do not change the underlying
frequency definition. Avoid baking MIDI's key range into the common degree type.

Authored performance events reference tuning degrees and scores. Preparation
resolves them to one authoritative `pitch_hz`; retain authored degrees as
provenance. A frequency measurement already in Hz needs no scale assignment.
Specify whether pitch bend acts before or after retuning, with explicit scope
and range. Repeated same-key triggers retain independent identities.

Sample playback relates event frequency to the slot's reference frequency;
oscillators consume Hz. MIDI and CV bindings report quantization and limitations
on independent pitches. These contracts can be designed and checked without
generating audio or implementing a sampler.

### Extraction and acceptance

Extract musical definitions and pure calculations from Tuney's `Tuning`,
`Computed`, `Ratios`, `Table`, and `Scale`. Keep UI annotations, file dialogs,
and fallback selection local. `Table.__call__` currently uses modulo indexing
to keep Tuney's instrument playable; that is explicitly not the finite-table
contract. Review the host mapping when adopting the new model rather than
silently copying that fallback or changing Tuney in this planning revision.

Use language-neutral fixtures for exact fractions, fractional powers, a
one-step equal-tempered pattern, a twelve-step just-intonation example,
non-octave cycles, negative degrees, finite ratio/Hz boundaries, Scala import,
and MTS per-key tables. Preserve Tuney examples where they express intended
musical behavior; identify intentional corrections separately. Define numeric
tolerances for irrational results. Parser, model, and pitch-value tests come
before any new waveform generation.

### Additional work beyond the prompt

None.
