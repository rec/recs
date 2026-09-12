# Future proposals

This is a suggested implementation order for extending Recs and Ufor. Existing
format documentation remains authoritative for what works today; the proposals
below are not a claim that every described feature is missing.

The order puts shared editing rules before the tools that need them, and makes the
slideshow the first new performance application. Build only the foundation each
milestone needs: a slideshow need not wait for all MIDI-CI, CV, or plugin work.
Production sampler and synthesis engines remain deferred. The next musical-model
step is to [settle a minimum envelope and voice-lifecycle contract](#minimum-envelope-and-voice-lifecycle-contract)
for one simple instrument, rather than wait for the entire musical model to be
finished. Waveform generation still requires an explicit decision to resume it.
Existing recordings and engines can support these proposals.

See [Deferred work](deferred-work.md) for the musical-model and engine decisions
and [Verification procedures](verification-procedures.md) for the wider roadmap.

## Suggested implementation order

| Step | Useful outcome | Main dependency |
| --- | --- | --- |
| 1 | [Give controls a shared meaning](#sampled-quantities-curves-and-physical-controls) | Existing quantity and time types |
| 2 | [Make actions editable and replayable](#events-requests-and-sequences) | Time and control rules |
| 3 | [Combine reusable scores](#arrangements-sequences-and-nested-mixes) | Quantities and event playback rules |
| 4 | [Connect a score to one real implementation](#implementations-endpoints-and-parameter-mappings) | Named score inputs, outputs, and parameters |
| 5 | [Build the first new performance tool](#live-slideshow-format) | Timing, cues, and a minimal display binding |
| 6 | [Bring lighting into the timeline](#fixture-controls-dmx-and-spatial-light-fields) | Control curves and physical bindings |
| 7 | [Preserve what actually aired](#radio-programmes-live-sections-and-rebroadcast) | Arrangements, bindings, and run records |
| 8 | [Improve the tools through use](#future-features-worth-building) | Experience with the earlier tools |
| 9 | [Explore additional domains](#new-data-domains-and-interchange-formats) | A concrete need and representative data |

### Reading this plan

A **score** describes an editable work; a **run** records what happened in a
performance. A **host** plays or renders it. An **adapter** is installed code that
talks to a device or engine; a **binding** supplies its mappings and local
settings. A **sealed asset** is a file identified by its recorded size and hash.
Named inputs and outputs are score connections, not network ports.

Examples illustrate behavior. Unless linked to an implemented specification, they
are design sketches rather than loadable scores. Each section starts with its
purpose and first useful result, followed by the detailed rules.

## Sampled quantities, curves, and physical controls

**Milestone 1: Give controls a shared meaning.** Start with the scalar controls
needed by the next feature. Add dense arrays and physical CV delivery when a
concrete device needs them.

**First useful result:** Edit gain, frequency, and gate curves without confusing
their units. Check interpolation, defaults, and competing writers.

**Implemented scalar profile:** Ufor now provides editable automation scores,
TOML round trips, JSON Schema, and a pure evaluator for these three quantities.
See the [automation format](../../../ufor/doc/automation-format.md) and
[portable cases](../../../ufor/conformance/automation.json). Direct-writer
conflicts and explicit add/multiply contributions are checked within a score.
Graph-wide ownership, GUI editing, dense arrays, physical delivery, and the
broader quantity proposals below remain later work.

### Quantity types

A numeric stream declares both what a value means and how it is represented. The
semantic quantity, unit, scalar type, shape, and timebase are required. The range
is a domain constraint, not a substitute for a unit.

| Quantity | Canonical meaning | Typical representation |
| --- | --- | --- |
| Audio amplitude | Linear amplitude relative to declared full scale | Float samples, time by named channels |
| Gain | Linear multiplier; zero is mute and one is unity | Scalar or curve |
| Level | Decibels with reference named, such as dBFS | Analysis stream or processor parameter |
| Frequency | Hertz, with positive values where pitch is defined | Scalar, curve, or sampled control |
| Expression | Named dimensionless unipolar or bipolar control | Curve or control-change event |
| Position/orientation | Named coordinate frame, metres or degrees | Vector quantity |
| Voltage | Volts relative to the endpoint's electrical reference | Sampled array or curve |
| Gate | Logical inactive/active state | State-change events, rendered to voltage by a binding |
| Light | Linear color components and intensity in a declared color space | Spatial field described in [Lighting](future-proposals.md#fixture-controls-dmx-and-spatial-light-fields) |

Do not treat a number in `[0, 1]` as interchangeable across these types. A gain of
0.5, a MIDI expression of 0.5, and a 0.5 V signal have different meanings. Use
explicit conversion nodes. A parameter schema fixes its canonical unit, so every
value need not repeat that unit. Editors may display convenient units and convert
before saving. Schema units can map to existing vocabularies; LV2 already
describes units on inputs and outputs and some conversions. [LV2
Units](https://lv2plug.in/ns/extensions/units).

### Sampled arrays

A sampled stream specifies rate, ordered named axes, scalar encoding, and
quantity. Audio names its channel layout explicitly. A channel index is zero-based
in this proposed model; device channel numbering belongs in the binding.
Reshaping, selecting channels, downmixing, and rate conversion are declared
operations. DSP may exceed audio full scale internally; clipping or limiting
belongs to the output contract, not every intermediate array.

A fragment connects asset frame zero or another asset offset to a native timeline
position and frame count. The session record describes missing intervals. Filling
an audio gap with zero for listening does not turn lost samples into measured
silence.

### Curves and parameter automation

A curve contains ordered `{tick, value}` knots and interpolation `hold` or
`linear`, plus a timebase and target quantity. Knots are strictly increasing.
Before the first knot use the instance's base parameter value; after the last knot
hold its value. A clip limits the interval over which its curve is active.

`hold` is mandatory for enums, gates, and booleans. Linear interpolation operates
in the declared canonical unit. A logarithmic frequency sweep must use an explicit
log-domain mapping; it is not a host preference. Equal-power audio crossfades are
a paired mix operation, not a generic interpolation for arbitrary quantities.
Preserve an existing standalone equal-power gain lane by storing linear knots in
squared gain and applying an explicit nonnegative square-root mapping. This
reproduces `sqrt((1-t)*a*a + t*b*b)` without treating that rule as interpolation
for voltage, pitch, or an enum. With no instance override, the base parameter
value is its declared default.

At a parameter, a direct automation lane replaces the base value. Additional
modulation is allowed only through a declared combiner such as additive volts or
multiplicative gain. Reject competing writers without one. Scope can be global,
part, or voice; its lifetime must match the owning object.

### CV and gates

Keep pitch in Hz, expression dimensionless, and actual measured/output voltage in
volts. A pitch-to-voltage mapping names reference frequency `f0`, reference
voltage `v0`, and volts per octave `s`: `v = v0 + s * log2(f / f0)`. For a chosen
profile with `f0 = 440 Hz`, `v0 = 0 V`, and `s = 1 V/octave`, 880 Hz requests 1 V.
This is an example calibration, not a universal device standard. Linear Hz/V and
other devices need their own mappings.

An endpoint profile must specify supported electrical range, calibration, output
rate, gate levels, and stop/disconnect state. “5V control” alone does not specify
polarity, pitch law, or permissible input voltage. The plan must not assume that
an arbitrary audio output can produce calibrated DC.

Declare out-of-range behavior as reject or clamp, with any clamping reported.
Separate a logical gate from its physical active voltage. A short trigger pulse
has an explicit duration and minimum supported sink resolution. On transport stop,
apply the profile's idle values; zero volts is not universally silence.

### Analysis results

An audio-to-pitch processor emits frequency plus a separate validity/confidence
signal. Zero Hz is not a substitute for “unvoiced.” A feature record identifies
the input observation interval, effective timestamp, and the later time at which
the result became available. Offline alignment can place the result at the
analyzed moment; live routing respects the analysis delay.

Keep loudness, envelope, onset events, and spectral arrays as distinct types.
Derived streams reference the source and processor run so a user can regenerate
them without confusing them with the original measurement.

### Integration notes

Recs audio blocks remain efficient NumPy arrays at runtime. Add descriptors around
stored and routed streams, not one Python object per sample. Recsam's `Control`
polarity/default becomes a dimensionless specialization of the common parameter
contract. Preserve the existing distinction between linear edit gains and recsam
decibel parameters during conversion. Voltage and feature validity are new
contracts; neither can safely inherit audio defaults.

## Events, requests, and sequences

**Milestone 2: Make actions editable and replayable.** Reuse the event envelope,
then specify seeking, looping, and note ownership. Add a small UMP representation
before expanding device-specific MIDI support; MIDI-CI host integration can follow
later.

**First useful result:** Crop, loop, and seek a sequence without stuck notes or
accidental external actions. Preserve raw MIDI and UMP data, including unknown
messages.

### Remaining scope

The milestone 2 library profile is implemented in Ufor: `SequenceSelection`,
`state_at`, and `plan_playback` provide half-open selections, control snapshots,
active-note retrigger/omit policies, loop-qualified ownership, and end cleanup.
Raw captures remain inert. `UmpEvent` preserves exact packet words, checks packet
length, exposes known groups, and distinguishes SysEx7 from SysEx8 packet families.
Portable conformance examples and the host application contract are in
[Ufor's sequence playback specification](../../../ufor/doc/sequence-playback.md).

Host transport integration, MIDI-CI handling, SysEx reassembly/conversion, and
request execution remain later work. The VL70m code remains a limited MIDI 1.0
proof of concept. This milestone introduces no audio generation or device output.

### Event envelope

Each stream declares its timebase and permitted event schema. Each event has
`tick`, `ordinal`, `kind`, and a typed payload. The ordinal breaks timestamp ties
and also identifies the event within its stream. Source identity and capture-clock
observations belong to its recording context. Authored sequences use the same
records as captured semantic event streams.

| Event family | Payload and identity |
| --- | --- |
| Performance | Trigger, release, and scoped control change; part and trigger ID |
| Key | Physical key identifier, logical text when available, press/release, modifiers, repeat flag |
| Parameter change | Structured destination, typed value, and scope |
| Cue | Named timeline marker or transport cue, with a declared action |
| Request | Named endpoint operation, typed arguments, request ID, and replay policy |
| Result | Request ID, observed completion time, outcome, and typed result or error |
| Raw protocol | Protocol identifier, exact payload bytes, direction, and transport metadata |

Trigger IDs identify an active performance instance, not a pitch. Two overlapping
notes on the same key must have distinct IDs and independently match releases.
Retain recsam's `part`, `trigger_id`, normalized velocity, and optional
`pitch_hz`. A zero-velocity semantic trigger remains a trigger. MIDI's
interpretation of particular wire messages belongs to its adapter.

Illustrative inline sequence body:

```toml
timebase = "audio"
event_schema = "recs.performance"

[[events]]
tick = 0
ordinal = 0
kind = "trigger"
part = "lead"
trigger_id = "note-1"
key = 69
velocity = 0.8
pitch_hz = 440.0

[[events]]
tick = 48000
ordinal = 1
kind = "release"
part = "lead"
trigger_id = "note-1"
```

At 48 kHz these events hold a note for one second; its audible release tail
depends on the instrument. A sequence declares its extent separately from the last
event so trailing silence or held control state is representable.

### Raw capture and semantic editing

Preserve raw MIDI or OSC when fidelity to an unknown device matters. An editable
interpretation is a separate derived stream that records its mapping and the
source events it came from. Raw and semantic streams are related representations,
not two sets of commands to dispatch simultaneously.

MIDI adapters own channel/part mapping, overlapping-note matching, controller
resolution, sustain interpretation, and conversion to pitched performance. Keep
SysEx or other unrecognized messages as typed raw data. Export to a more limited
protocol reports quantization and unsupported per-note expression.

### MIDI 1.0 and MIDI 2.0 boundary

The event envelope is transport-neutral. A raw MIDI event therefore records a
protocol family and exact wire representation, rather than treating a list of
seven-bit bytes as the universal MIDI form. MIDI 1.0 byte streams, Standard MIDI
Files, and UMP are distinct encodings of related musical meaning.

The first MIDI 2.0 work defines a small UMP layer before adding more
device-specific MIDI formats. It must represent MIDI 1.0 messages carried in UMP,
native MIDI 2.0 channel-voice messages, group assignment, and exact UMP packet
words. It also distinguishes SysEx7 from SysEx8. A captured UMP stream preserves
its packet sequence even when no semantic adapter understands a manufacturer
message. Conversion to a MIDI 1.0 byte stream is an explicit lossy operation when
the source uses MIDI 2.0-only precision or expression.

MIDI-CI discovery, Profiles, and Property Exchange describe a device's current
capabilities or exchange protocol. They do not silently alter an instrument
definition, binding, or saved patch. A host may record them as raw protocol or run
observations, then use an explicit adapter to select a compatible binding.
Permanent descriptions of an instrument's musical interface remain separate from
discovery responses and connected-device state.

The [VL70m SysEx proof of concept](../../../ufor/doc/vl70m-sysex-example.md) is
deliberately a MIDI 1.0 byte-stream implementation. It preserves unknown bytes and
performs bounded patch relocation; it neither models UMP nor claims that the VL70m
supports MIDI 2.0.

OSC capture keeps address, type tags, arguments, bundle membership, raw bytes, and
source timetag where present. An address alone does not tell us whether a message
is state, a trigger, or a request with side effects. Its endpoint profile supplies
that interpretation. Bundles and typed arguments come from the [OSC
specification](https://opensoundcontrol.stanford.edu/spec-1_0.html).

Keys need both physical identity and optional resulting text: the same physical
key can produce different text under another layout. Replaying a captured key
sequence into an instrument uses an explicit key mapping. Sending it to the
operating system is a separate endpoint action, never an effect of opening it.

### Requests and effects

A request schema names an operation such as `set_parameter`, `start_recording`, or
`take_live_source`, with concrete argument types. Do not put arbitrary shell
commands, HTTP templates, or Python expressions into universal event bodies. An
installed adapter implements the operation and owns transport details.

The operation declares whether it is state-setting, repeatable, or a one-time
action. Capturing a request does not authorize its later execution. Offline
rendering and seek reconstruction simulate requests or retain them as events; only
a run explicitly binding an enabled action endpoint can dispatch them. Recording a
request's result does not guarantee the same result on replay.

### Editing, loops, and seeking

A sequence clip selects a half-open event interval and translates its timestamps
using [Arrangements](future-proposals.md#arrangements-sequences-and-nested-mixes).
Include parameter state at its start through a checkpoint or replay.
Start-inside-note behavior is explicit: `retrigger_active` creates a new scoped
trigger at the clip boundary; `omit_active` waits for subsequent triggers. The
former restarts envelopes and does not reproduce the sound of a sustained voice
already in progress.

At a clip end, release all triggers owned by that clip and let the arrangement's
tail policy determine retained output. At a loop boundary, close that iteration's
trigger ownership and reconstruct the next iteration's starting state. Qualify
each trigger ID with its clip and loop iteration so repeated clips cannot release
one another's notes. Requests with effects are not repeated by a loop unless its
execution policy allows it.

### Integration notes

The performance types now live in `ufor.events`, using the common `tick` and
`ordinal` envelope. Recs imports them directly and its former event module is
removed. Common sequences and native JSONL share these types. The [instrument
contract](../../../ufor/doc/instrument-format.md) records their scope and
lifecycle boundary. Preserve MIDI and OSC capture data and its original timing
during conversion. Tuney's `CharPress` maps to key events; its private cached
character and callback handles remain runtime details. Keep recorder status events
as run observations; they are not automatically commands to execute during
playback.

## Arrangements, sequences, and nested mixes

**Milestone 3: Combine reusable scores.** Extend existing audio arrangements to
events and controls. Reuse current composition machinery and identify unsupported
cases before adding fields.

**First useful result:** Combine recorded audio, a control curve, and an event
sequence. Reuse a nested score twice with independent state and timing.

**Implemented profile:** Ufor arrangements already resolve named audio parts,
event connections, nested score instances, and selected audio clips. This
milestone adds a reusable automation score's public `control` output and an
arrangement `control_clips` placement. The curve's target selects a sibling
part's public parameter. Resolution checks the output contract, target, exact
clock conversion, parameter unit/scope/range, and one writer per target. An
audio request includes the curve from its clip start through the requested end,
which preserves its state for cropped rendering. The worked composition test
contains a recorded audio clip, a sequence driving an instrument, and a control
curve targeting a light-score parameter. See [Ufor's arrangement
format](../../../ufor/doc/arrangement-format.md) and [automation
format](../../../ufor/doc/automation-format.md).

The profile deliberately supports part-scoped numeric controls at speed one.
Logical gates, voice/instrument scopes, control combiners, tempo anchoring,
audio time-stretching, reversal, and host audio/device execution remain later
work. Raw event captures stay inert unless an explicit adapter interprets them.

### Sources and clips

A source references a recording stream, a sequence, an instrument-driven graph,
another arrangement's exported output, or a declared live endpoint. File assets
become source nodes through their typed reader. In-memory materialization is an
execution detail, not a portable source locator.

A clip names its source and lane, a source interval, a timeline start, and a
positive rational playback speed. Source positions use the source timebase;
timeline positions use the arrangement timebase. Resolve to physical time before
applying speed. For source interval `[a, b)`, start `s`, and speed `r`, source
time `u` appears at `s + (u-a)/r`, and duration is `(b-a)/r`. Final
sample-boundary conversion follows
[Time](verification-procedures.md#time-clocks-and-transport).

The first profile uses speed 1. Audio speed changes require a selected resampling
or time-stretch operation, with its pitch behavior explicit. Musical clips can
follow a parent tempo map when marked beat-anchored. A physical recording stays in
physical time unless explicitly warped. Reversal is an operation, not a negative
speed quietly applied to requests and note lifecycles.

At 48 kHz, selecting frames 48000 through 528000 from an interview and placing
them at timeline frame zero plays ten seconds from its one-second point. The clip
selects a named part's output. See the [implemented audio arrangement
example](../../doc/arrangement-format.md).

### Mixing and automation

Routes connect explicit inputs and outputs. Numeric audio summing, event merging,
control selection, and lighting blending are distinct operations. A track with
overlapping clips declares its overlap rule; unsupported combinations fail
validation. Stereo audio does not automatically become mono, and MIDI events do
not become sound without an instrument.

Clip gain is a linear audio multiplier. General effects are processor nodes. A
crossfade names both clips, its interval, and curve law; preserve the existing
equal-power behavior as a named audio mix contract. Existing independent
equal-power gain lanes use the squared-gain mapping in
[Quantities](future-proposals.md#sampled-quantities-curves-and-physical-controls).
Parameter automation uses the common structured target and curve rules. Multiple
control writers require an explicit combiner, including manual overrides and
automation.

Rendering declares a finite requested interval and a tail policy: truncate at the
end or retain a specified additional duration. Delays, release envelopes, and
reverberation may continue after the last clip. An open-ended live source does not
make an offline render silently infinite.

### A mix of mixes

An arrangement dependency exposes named outputs and optional exported parameters.
Its internals retain a private namespace. Every instance has its own state, time
mapping, and voice ownership. Definition-reference cycles are invalid even when a
contained DSP operation has internal feedback.

An outer clip can select a range from an inner arrangement. The compiler can
flatten or cache it only when it preserves state, pre-roll, tails, and parameter
scope. A cached render records definition/dependency digests and the realized
binding. A changed instrument or plugin binding invalidates that cached result.
Cache implementation is optional; correct nesting is not.

Keep authoring recipes separate from the resulting work. A recipe such as “trim
silence, calibrate, then mix” produces an arrangement and any derived assets.
Retain the recipe as provenance if useful, but playback does not need to execute
CLI strings to discover what the work means.

### Integration notes

Recs already uses Ufor arrangement scores, named parts and outputs, and separate
render destinations. Extend that foundation rather than repeat the migration.
Preserve existing integer-frame audio editing and rendered results.

Editing recipes such as CompositionEdit describe authoring operations. Their
result should remain a score that can play without rerunning those commands. Keep
whole-program normalization an explicit offline operation; it cannot be promised
for unknown future live audio.

## Implementations, endpoints, and parameter mappings

**Milestone 4: Connect a score to one real implementation.** Build the smallest
binding needed for one existing driver. A general plugin host is a later project.

**First useful result:** Preview a score and send it through one real adapter.
Check parameter conversions and report unsupported capabilities before output
begins.

**Implemented profile:** Ufor now has `BindingScore`, a portable declaration of
a referenced definition, named host adapter, implementation revision,
capabilities, and parameter maps. Pure conversion supports identity, affine,
log-normalized, and ratio-to-dB parameters, rejecting invalid ranges and making
silence an explicit native mute. The first concrete identity is
`sysexy.vl70m`, for the existing VL70m SysEx librarian; it validates material
but does not open a MIDI device. See [the binding format](../../../ufor/doc/binding-format.md).

Host adapter lookup, display/output selection, credentials, and actual device or
plugin activation remain host work. No hardware was contacted by this milestone.

For example, a score asks for a filter cutoff in Hz. A binding translates that
value into the selected device's parameter and records any limitations.

### What a binding contains

A binding score names the logical definition or endpoint, an installed adapter
name, implementation identity/revision, input/output channel mapping, parameter
mapping, and supported capabilities. Physical bindings additionally identify local
device selectors and calibration. Credentials are resolved through local
configuration and are never included in the portable content package.

An installed adapter owns executable code, plugin discovery, library loading, wire
serialization, and calls into the implementation. A definition contains registered
operation IDs, not executable module paths. Built-in DSP, external plugin hosts,
existing application engines, and hardware endpoints can all implement this
contract without sharing a single binary ABI.

The capability declaration includes exact stream types and rates, parameter
domains and update resolution, live/offline support, latency, state restore,
determinism claim, and available failure observations. A host validates the
selected graph against it before activation. Unknown required capabilities fail
preparation; an editor can still display the unbound definition.

### Parameter mapping

Every mapped parameter names a canonical parameter name, a stable native
identifier, conversion, valid input/output ranges, and automation resolution.
Native display names are labels, not stable identifiers. A mapping can be
identity, affine, logarithmic, a monotone piecewise table, or an explicit enum
table. Anything more complex is implemented by an adapter with a named tested
contract, not embedded code in TOML.

Illustrative binding body for a hypothetical plugin with normalized logarithmic
cutoff. It makes no claim about a particular real plugin:

```toml
adapter = "example.plugin-host"
implementation = "example.filter"
implementation_revision = "1"

[[parameters]]
parameter = "cutoff_hz"
native_id = "cutoff"
conversion = "log_normalize"
input_min = 20.0
input_max = 20000.0
output_min = 0.0
output_max = 1.0
out_of_range = "reject"
```

For this mapping, `y = log(x/20) / log(20000/20)`. The endpoints map to 0 and 1;
their geometric mean maps to 0.5. Do not use a linear map because both endpoints
fit. An inverse mapping exists here, but an enum table or quantized mapping may be
many-to-one; feedback must then be reported as quantized/ambiguous rather than
falsely reconstructing the original value.

For amplitude gain, converting a positive multiplier `g` to decibels uses `20 *
log10(g)`. Zero maps to an explicit native mute or supported silence value; it is
not a finite dB value. Likewise, a fixture's unsupported gobo has no nearest
numeric meaning. Reject or require an authored substitution.

Plugin APIs expose their own parameter identities, ranges, flags, and automation
contracts. For example, CLAP's parameter interface describes parameter metadata
and parameter update behavior. Adapters must honor those contracts, rather than
assuming every knob accepts arbitrary per-sample updates. [CLAP parameter
interface](https://github.com/free-audio/clap/blob/main/include/clap/ext/params.h).

### Controls entering the graph

An input binding selects a physical control or protocol field and maps it to a
typed logical control. It declares source domain, target domain, conversion,
scope, and state reset. MIDI CC, OSC, keys, and sensor data become explicit
event/quantity streams. Routing those streams through common mappings removes
protocol interpretation from instruments and animations.

If a manual control and an automation lane both address a parameter, the work
declares priority, latch, or a mathematical combiner. A host UI must not invent a
different precedence on each machine. Record manual changes with their resolved
target and original source when reproducing the run matters.

### Portability levels

| Claim | Required evidence |
| --- | --- |
| Editable | Score schema and dependencies can be inspected without executing the implementation |
| Realizable | A selected binding satisfies the required port and parameter contracts |
| Behaviorally matched | A named operation contract has conformance examples and a declared tolerance |
| Captured result | Sealed output assets preserve the produced data irrespective of future plugin availability |

An approximate implementation is an explicit authored choice, recorded in the run.
Never substitute one silently because its name contains “compressor.” Opaque
plugin state may supplement canonical parameters for implementation-only details.
Restore opaque state first, then apply all canonical mapped parameters; canonical
values win. A binding that cannot honor this order must reject mixed
state/parameter restoration. Missing implementation means that opaque state is
inspectable as an asset but not portable behavior.

### Integration notes

Replace Lyte's score-level Python `impl` resolution with adapter lookup at
preparation time. Move `DmxInstrument` patch fields, Twinkly connection fields,
and Streamo device/service selection into binding responsibilities as each
application adopts the format. Reuse actual drivers and service adapters; do not
rewrite network transports to make the score model uniform.

Showco continues owning operational setup and service actions. Ufor owns the
portable score model; Recs and the other hosts execute it through their selected
bindings. Plugin hosting is a new implementation task, with a single concrete host
chosen for the first integration. The format proposal does not require adding
every plugin SDK as a dependency.

## Live slideshow format

**Milestone 5: Build the first new performance tool.** Prioritize the long-planned
slideshow once timing and a minimal display binding are ready. Start with still
images, bulk selection, crops, accessible text, and manual or timed advance. Add
video assets and accompaniment in subsequent increments of the same format.

**First useful result:** Resolve directories and exclusions, finish with two
explicit images, edit their crops and timing, and replay a recorded manual
presentation. Include accessibility in the first usable player.

**Implemented profile:** Ufor now has a still-image `SlideshowScore` with sealed
assets, ordered slides, normalized crop/rotation/fit, required alt text, manual
or cue advance, adjacent transitions, and ordered run records. Its pure resolver
sorts host-supplied relative paths and applies declared inclusion/exclusion rules.
See [the slideshow format](../../../ufor/doc/slideshow-format.md). Image/video
decoding, display output, audio accompaniment, captions, and cue delivery remain
host work.

A slideshow is an ordered visual performance: it can play automatically, be
advanced by a person, react to a cue, or mix those modes during one run. It is
editable without opening an image or video codec. Still images are its primary
material; video clips are allowed as visual assets. General video editing and
codec implementation remain outside this plan.

### The score

A slideshow score contains named visual assets, ordered items, optional audio
accompaniment, caption tracks, image descriptions, cues, and a default run policy.
Each item has a stable name. Its visual source is either an explicit asset or a
declared directory selection. A directory selection is resolved to explicit items
when it is imported or sealed, so later directory changes cannot silently alter an
authored show.

An item has a display interval in the slideshow timebase. A still image needs a
positive duration. A video clip selects a finite source interval and has a
declared playback speed of one in the first profile. Its embedded audio is mute
unless the score explicitly supplies it as an accompaniment source. This keeps
visual editing and audio accompaniment independent.

Visual placement declares a normalized crop rectangle, rotation in right-angle
steps, and a fit rule: `contain`, `cover`, or `stretch`. Cropping changes only the
item's view of the asset. A display binding chooses an actual screen, projector,
resolution, color conversion, and image/video decoder.

### Ordering and bulk selection

A bulk selection is an authoring instruction, not a vague filesystem lookup. It
names a relative directory, whether to recurse, inclusion and exclusion patterns,
and an ordering rule. The first profile supports `path` ordering by Unicode
code-point order of normalized relative paths. A later natural or capture-time
order needs its own specified comparator.

The selection resolves only regular files beneath the score root. It rejects paths
that escape the root through `..` or a symlink. Patterns apply to the normalized
relative path, use `/` as a separator, and do not match directories by themselves.
The resolved result records each source asset's path, byte length, and SHA-256. An
empty selection is an error unless it is explicitly marked optional.

The selection may be followed by ordinary explicit items. This expresses “play
these directories, excluding these files and patterns, then finish with these two
images” without special end-of-show fields:

```toml
[[selections]]
name = "travel"
directory = "photos/travel"
recursive = true
include = ["**/*.jpg", "**/*.png"]
exclude = ["**/draft-*", "**/duplicate.jpg"]
order = "path"
duration = { seconds = 8 }

[[items]]
name = "closing-sunrise"
asset = "photos/finale/sunrise.jpg"
duration = { seconds = 12 }

[[items]]
name = "closing-map"
asset = "photos/finale/map.png"
duration = { seconds = 12 }
```

Resolving the selection creates one item per matching asset, in the declared
order, before `closing-sunrise` and `closing-map`. The author may then edit any
resolved item, move it, replace its crop, or remove it. The original selection
remains provenance and can be deliberately re-resolved as a new edit operation; it
never changes the existing order by itself.

### Transitions and timing

Each item starts after its predecessor's display interval, except where an
explicit transition overlaps them. A transition belongs to the boundary between
two named items and declares a nonnegative duration no longer than either visible
interval. The first profile has `cut`, `crossfade`, and directional `wipe`; a host
rejects an unsupported transition instead of substituting one. A zero-duration
transition is a cut.

Cues are typed events with a slideshow position and ordinal. They may mark a
slide, arm an operator action, or expose a named output for a binding. The
definition records no executable shell command, network request, or device
address. A binding decides whether a named cue controls lights, sound, a screen,
or an operator interface.

### Audio accompaniment and captions

An accompaniment is a separate audio source, such as a recording stream or audio
asset, with an explicit slideshow start position and finite source range. It may
begin before the first visual item or continue after the last one when the
requested render interval includes it. Visual advance never trims or seeks the
accompaniment unless the authored run policy says so.

Every audible accompaniment needs a caption track for the hearing-impaired. A
track declares language and contains ordered, non-overlapping timed captions with
text and optional speaker name. It may instead reference a sealed WebVTT, TTML,
IMSC, or EBU-TT asset when preserving a source format matters. Captions use
slideshow time, including an explicit offset from their audio source, so a host
does not guess synchronization from filename or duration.

```toml
[accompaniment]
asset = "audio/narration.flac"
start = { seconds = 0 }

[[captions]]
start = { seconds = 2 }
end = { seconds = 5 }
language = "en"
speaker = "Tom"
text = "The first train arrived before sunrise."
```

### Image descriptions

Every visual item has an authorable text description for visually impaired
audiences. `alt` is a concise identification suitable for immediate screen reader
output. `description` is an optional longer account. Both describe the authored
crop and item context, not merely the source filename. A video item also provides
a description of its visual action or refers to timed audio description cues when
that action changes during the clip.

Descriptions are part of the editable item. They are not generated from image
analysis, hidden in display-specific metadata, or replaced when an asset is
renamed. A host can present `alt` at item entry and make the longer description
available on demand without changing the visual timeline.

### Live performance and run records

The score's times describe the planned presentation. Manual holds change the
actual run, whose timestamps must be recorded separately. Before implementing
accompaniment in manual mode, choose and document whether audio continues, pauses,
or seeks when visuals move. Captions must follow the audible audio position; image
descriptions follow the displayed item. Do not let the host guess this
relationship.


The default policy is one of `automatic`, `manual`, or `cue`. Automatic items
advance at their scheduled boundary. Manual items hold until an explicit operator
advance. Cue items hold until their named cue occurs. The performer may safely
advance, go back, hold, jump to a named item, or temporarily take manual control;
each action is an observed run event.

A run record captures the resolved asset list and hashes, entered items,
transition starts, operator actions, delivered cues, caption presentation, and
display failures. Returning to an earlier item is an observable choice, not a
rewrite of the authored timeline. An as-presented replay follows recorded
decisions; a fresh performance follows the definition and current binding.

### Preparation and validation

Preparation verifies assets, resolves selections, validates transition bounds,
checks that all caption intervals are valid, and requires `alt` for every item. It
reports a video asset whose selected source interval or decoder is unsupported.
Keep pure score validation separate from host readiness checks. The host checks
decoders, display support, and audio output before a performance.

The portable package holds image and video assets, audio accompaniment, caption
assets when used, the resolved slideshow definition, and optional run records.
Each dependency remains relative to the package root and sealed by byte length and
SHA-256. A missing optional visual may use a declared replacement item; a missing
required visual or accessible text is a preparation failure.

### Build in small steps

This is a format plan. The next implementation work is a pure schema and selection
resolver with language-neutral cases for ordering, exclusions, transitions,
captions, descriptions, and recorded manual decisions. Image/video decoding,
screen output, cue delivery, caption rendering, and audio playback belong to hosts
and bindings. A later decision may add richer crops, animation, multiple displays,
live camera inputs, or new transition contracts.

## Fixture controls, DMX, and spatial light fields

**Milestone 6: Bring lighting into the timeline.** Reuse Lyte drivers. Begin with
one fixture profile and one pixel layout before broadening device coverage.

**First useful result:** Repatch a fixture or rewire a pixel string without
editing its cues. Preview and delivery use the same values and layout, with
explicit stop behavior.

**Implemented profile:** Ufor now has `FixtureScore` for semantic numeric and
discrete fixture cues, plus separate `FixturePatch` records that map logical
fixtures to display and Art-Net wire universes and DMX start slots. Repatching
validates coverage without changing cues. Existing Ufor light layouts and wiring
continue to provide the independent pixel-field representation. See [the fixture
format](../../../ufor/doc/fixture-format.md). DMX/Art-Net transmission, fixture
channel encoding, preview, and stop behavior remain host work.

Lighting has two principal editable forms: semantic fixture state and spatial
fields. Raw device traffic is a third capture representation. Keep all three
distinguishable.

### Fixture state

A fixture definition exposes named typed parameters: intensity, color, pan, tilt,
strobe, gobo selection, or device-specific functions. Continuous parameters use
quantities with units or a declared normalized domain. Discrete modes use enums
and hold interpolation. A fixture profile maps these to the selected device mode's
channels, packed values, and ranges.

Use degrees for a calibrated pan/tilt interface where the physical meaning is
known. Retain an explicitly named normalized-position interface when it is not; do
not label an arbitrary DMX fraction as a measured angle. A profile documents which
semantic operations a fixture cannot perform.

Two lighting sources do not automatically add like audio. A compositor declares
per-parameter rules, such as maximum intensity, ordered override, or color blend.
Discrete gobo selections never average. Competing writers to a patched address are
a validation error unless the installation declares the compositor.

### DMX and Art-Net

An authored cue targets logical fixtures and parameters. A binding supplies
fixture mode, universe, starting slot, and endpoint. This allows re-patching a
show without rewriting every cue. Keep raw DMX snapshots as ordered byte arrays
with explicit slot count and universe identity when exact capture matters. Raw
playback requires a matching patch contract and bypasses semantic remapping.

Art-Net is an output/capture transport for the selected representation, not a new
semantic quantity. Specify raw wire address and human display universe separately.
The current Lyte driver translates `universe + universe_offset` to the wire
address, normally using offset -1. Carry that choice into the binding explicitly;
do not infer it from a bare universe number.

Bindings declare multi-byte channel order, slot offsets, quantization, and
discrete value tables. For example, a profile may encode a 16-bit value into a
coarse and fine slot; this is different from driving two independent dimmers. Keep
packet sequence numbers and arrival timing in raw capture provenance.
Multi-universe output needs a declared synchronization strategy and measured skew;
saving equal timestamps does not prove simultaneous physical presentation.

### Pixel geometry

A pixel field is an array over stable element names, with color components and
optional alpha defined by its schema. It references a layout containing ordered
elements, coordinates, coordinate units/frame, and named regions. Lines, matrices,
rings, wearables, irregular meshes, and spatial arrangements are all layouts of
elements. Matrix row/column addressing is an authoring view of the same stable
names.

Illustrative small layout body:

```toml
coordinate_unit = "metre"
coordinate_frame = "installation"

[[elements]]
name = "left"
position = [0.0, 0.0, 0.0]

[[elements]]
name = "right"
position = [0.1, 0.0, 0.0]

[[regions]]
name = "pair"
elements = ["left", "right"]
```

Store pixel order explicitly. A separate physical patch maps element names to
device and LED indices. Rewiring a string changes that patch, not the animation.
An animation that depends on distance consumes coordinates; one that chases along
a path consumes a declared ordered region. Missing geometry is an error for the
former, not permission to assume the pixels form a line.

Use a specified linear RGB working space for the first field profile, with
explicit conversion at device output. Calibration, transfer curve, component
order, RGBW conversion, quantization, and power limiting belong to the device
profile. Do not silently call all normalized RGB arrays linear. Color fidelity
across different devices needs calibration and is not guaranteed by shared channel
names.

### Time and playback

An authored animation graph generates fields from timeline position, parameters,
and declared state. A recorded field stream keeps actual frame timestamps and
layout identity. State changes hold until the next change unless a semantic curve
specifies interpolation. A sink schedules at its supported refresh rate and
reports dropped updates; the recording retains original timing.

Stop/disconnect behavior belongs to the endpoint profile: blackout, fade, or
defined held state. Resetting all raw bytes to zero is not a universal semantic
“off” for every fixture function. Preview uses the same layout and control
resolution as physical output, with delivery replaced by visualization.

### Integration notes

Keep Lyte's efficient frame arrays, renderers, and drivers. Introduce named
layouts and explicit color interpretation around them. Separate reusable fixture
capabilities from physical patching, retaining range and overlap validation. Adapt
existing show and installation models as each application adopts the common score;
check their current implementation at that point.

## Radio programmes, live sections, and rebroadcast

**Milestone 7: Preserve what actually aired.** Build programme transport after
arrangements, bindings, and run recording work together. Start with recorded
sections and one live input; add delayed relay and rolling buffers later.

**First useful result:** Run a recording, a cued live section, and a replacement
source. Replay the captured timing and decisions without needing the original live
input.

A broadcast score schedules content that may not exist yet. It describes intended
playout; a run records actual playout. A completed recording and a future
programme are different objects.

### Programme structure

A broadcast exposes programme outputs and contains ordered sections. Each section
names a source, scheduled start, duration policy, transition, and behavior when
content is unavailable. A source may be a recording, a nested arrangement, a live
input, or a live relay from another programme.

Every section uses exactly one start rule:

- `at`: a fixed position on the programme timeline, optionally anchored to UTC.
- `after`: begin after the named previous section actually finishes.
- `cue`: begin on an operator cue, with an earliest position and deadline.

Every section uses exactly one end rule: a fixed duration, a fixed end position,
or a cue/source-end bounded by a maximum duration. Reject cyclic `after`
dependencies. Unresolved cue timings make the plan provisional, not malformed.

Illustrative section within a one-hour programme whose `programme` timebase has
one tick per second:

```toml
[[sections]]
name = "guest"
source = "guest-feed"
start = { kind = "at", tick = 600 }
end = { kind = "at", tick = 900 }
transition = { kind = "cut" }
unavailable = { kind = "replacement", source = "standby-bed" }
late_join = "current"
capture = true
```

This reserves minutes 10 through 15. If the feed appears at 10:20, a `current`
late join takes its then-current content and still ends at minute 15. It does not
replay the missing 20 seconds. A replacement source must be prepared for the
entire reserved interval and declare its looping or end behavior.

### Three uses of live material

| Intent | Definition |
| --- | --- |
| Future live section | Logical microphone or contributor endpoint to be bound for this run |
| Live relay | Another programme's currently produced stream, with latency/buffer policy |
| Later replay of a live section | Sealed capture asset and its actual timeline placement |

A delayed relay additionally declares a required buffer duration. It can start
only when that amount of captured data exists. A source that has not happened yet
cannot be rendered ahead of time. Offline preparation may render the known
sections and show unresolved intervals, but must label that result incomplete.

The programme can be rebroadcast in two intentional ways. Replaying the captured
programme reproduces what aired. Running its definition again repeats recorded
sections and obtains new live material for its live sections. Selecting between
these creates a concrete replay arrangement or a new run; the player must not
silently choose according to whether a microphone happens to be connected.

### Transitions, overruns, and failures

An overlap requires an explicit crossfade or mix rule. At a hard start/end, apply
the declared cut/fade rule to the preceding source even if it overruns. A
follow-on section shifts with its predecessor. A cue-based section reaching its
deadline takes the authored action: use replacement, skip to a named section, or
stop the programme. These policies are visible editorial choices.

Availability distinguishes absent connection, insufficient buffered content,
decode failure, and valid silence. Silence alone does not prove a feed is dead.
Set a freshness criterion in the source binding, such as input progress, rather
than guessing availability from amplitude.

Record every actual start/end, switch, source instance, dropout, replacement,
operator cue, and output-delivery result. Capture the programme bus and, when
requested, the constituent live sources. An as-aired arrangement references these
captures and actual decisions so later rebroadcast never depends on recreating an
operator's choices from memory.

A failed delivery is not proof that nothing aired. Record source production, local
output submission, and remote delivery observations separately to the extent the
adapter can observe them.

### Application responsibilities

Recs resolves and renders content, journals decisions, and records programme
audio. Streamo delivers a selected programme output and supplies supported live
feed adapters. Showco presents run readiness, timing, actionable failures, and
operator cues. Lyte can consume synchronized programme controls through another
output. Scheduling is owned by one broadcast transport; applications must not
maintain competing copies of section position.

Streamo should accept a programme's audio output through an explicit binding.
Service credentials and its other video features remain deployment settings. Its
existing delivery support does not itself provide a radio rundown model.

Showco's `ActionResult`, action log, and service status remain runtime views. They
can report broadcast run observations without becoming the authoritative programme
definition. The planned/live/as-aired distinction is new functionality.

## Future features worth building

**Milestone 8: Improve the tools through use.** Choose these independent
follow-ups from experience with the earlier milestones.

**First useful result:** Choose one user-visible improvement, identify its
prerequisite, and define an observable acceptance case.

### Make the whole performance editable

| Feature | What the user gains | Prerequisite and boundary |
| --- | --- | --- |
| One multitrack editor | Audio waveforms, notes, controls, keys, fixture cues, and LED regions on a common timeline | Shared time and stream types; each lane still uses its own editing tools |
| Performance history | Select a moment and inspect what was heard, played, requested, and sent to lights | Capture journals and clock uncertainty; do not imply perfect synchronization |
| Semantic diff and merge | Review “cutoff changed from 800 to 1200 Hz” or “live segment moved 30 seconds” | Stable IDs and schemas; conflicting editorial choices remain visible |
| Named reusable scenes | Trigger a coordinated instrument, synth patch, and lighting arrangement | Explicit interfaces, instance state, and bounded transport behavior |
| Capture and replace | Freeze a processor or live performance into assets, then reopen its editable source | Provenance, state/tail rules, and dependency identity |

### Make performance instruments richer

Build on existing named slices. Consider linked microphone takes, reusable slot
groups, and voice retirement after their interactions are specified. A sample
browser could create an instrument directly from selected Recs recording ranges,
retaining the original take and edit provenance.

Reproducible humanization could vary timing, pitch, dynamics, and take choice from
a documented seed and algorithm. Keep authored randomness separate from the result
of one performance, so “try another take” and “repeat this take” are different
operations.

The first [modulation profile](deferred-work.md#envelopes-lfos-and-modulation) now
defines envelope/LFO state and curve semantics. Looped envelopes,
random/sample-and-hold sources, and continuous rate ramps remain later extensions
requiring their own conformance cases. Granular synthesis, convolution, time
stretching, and physical modeling are useful later processor capabilities. Prefer
binding an existing implementation when it meets the contract. Add a new universal
parameter only when its meaning across implementations can actually be stated.

### Sampler and synthesis work remain deferred

The [deferred musical work](deferred-work.md) owns engine selection, a possible
compiled sampler or VST, and language-neutral conformance tests. These are not
prerequisites for the slideshow, lighting, or broadcast milestones.

#### Minimum envelope and voice-lifecycle contract

The first step on this separate musical-model track is to settle the rules for
one simple instrument. Build on the existing envelope model and specify:

- How a trigger starts a voice and its envelope, including retriggering.
- How release, sustain-pedal changes, and legato affect the envelope and voice.
- Which trigger owns each voice, including overlapping notes of the same pitch.
- When a voice finishes, and how it is retired on stop or when capacity is reached.

The result should be a small written contract with concrete event sequences and
expected envelope states and voice lifetimes. Resolve the behavior of those cases
without choosing an engine language, plugin format, or adding waveform generation.

Next, turn the examples into portable conformance cases. Once those rules are
settled, a separately approved small reference renderer can test the design before
committing to a production sampler or VST. Finishing every tuning, LFO, or synthesis
extension is not a prerequisite for that experiment.

### Connect sound, gesture, and space

Offer reusable mappings such as breath to brightness, drum onset to a spatial
pulse, pitch to a palette position, or a keyboard gesture to a synth envelope.
Each mapping should expose its input domain, output domain, smoothing, and
latency. An editor could preview those relationships using a recorded input before
binding any device.

Layout-aware authoring could support paths, surfaces, nearest-element queries, and
transformations between installations. Explicit retargeting would let one
animation move from a ring to a wearable without pretending that their geometry is
identical. Calibration captures could describe actual brightness/color and CV
response rather than relying on factory labels.

Higher-dimensional quantities could cover position, motion, sensor telemetry, or
haptic controls. Add a typed schema and combination rule for each concrete use,
rather than making arbitrary arrays automatically routable to all devices.

### Better radio and live production

Add a rolling capture buffer for instant replay and delayed live relay, with
explicit retention limits and a clear boundary between retained and expired
material. A producer could turn the previous five minutes into a replay section
without interrupting ongoing capture.

A programme rehearsal view could substitute recorded stand-ins for future live
sources, display unresolved intervals, and estimate overrun against hard starts.
Loudness preparation could process known sections in advance while a separate live
chain manages unknown material; whole-program normalization remains an offline
operation.

An as-aired editor could compare intended and actual playout, replace a failed
remote interview with a later recording, and generate a clearly identified edited
rebroadcast. Preserve the original as-aired capture as its own work.

### Reproducibility and scale

Build render caching from sealed dependency identities, parameter values,
bindings, and state. Extend it to reusable stem/field renders only after correct
single-machine execution exists. A cache must include the selected realization,
not merely an abstract operation name.

State checkpoints could accelerate seeking and long offline jobs. Checkpoints need
implementation identity and precise event/clock position; restoring an
incompatible plugin state must fail visibly. Exposed causal feedback graphs can
follow once the scheduler honors sample-level delay independently of block size.

Distributed execution could place capture and outputs near their devices. It
requires measured clocks, bounded transport, ownership, and failure behavior; it
is a separate runtime project, not something achieved by putting hostnames on
graph nodes. Start with one transport authority and recorded observations.

### Interchange and accessibility

Provide an implementation coverage report before exchange: which parameters are
exact, which are approximate, what is unavailable, and which outputs have been
captured. Add plugin/device adapters one at a time with reusable mapping fixtures
and clear unsupported-feature reporting.

Schema-driven editors could supply appropriate controls for Hz, ratios, enum
choices, time, geometry, and tuning degrees. Accessible text authoring and
keyboard navigation should remain first-class alongside graphical timelines.
Human-friendly recipes can compile into the same canonical scores so an operation
authored in the CLI and one authored in an editor stay interchangeable.

## New data domains and interchange formats

**Milestone 9: Explore additional domains.** Keep this as a research backlog,
selecting a domain only when there is a concrete use case.

**First useful result:** Obtain a representative file, identify what must survive
editing, and demonstrate one useful round trip.

The earlier milestones cover slideshows, automation, cues, MIDI, device patches,
lighting, CV, analysis, broadcasts, and interactive performance capture.

Further possibilities include stage automation, spatial audio, notation and
rehearsal material, robotics and kinetic sculpture, haptics, environmental
measurements, interactive-installation sensors, projection mapping metadata,
networked collaborative state, score following, digital fabrication, and
accessibility tracks. Projection mapping may describe surfaces, transforms, masks,
calibration points, and still-image placements; it does not add general video
editing or video codecs to the proposal.

### Formats and technologies to investigate

This inventory mixes file formats, transport protocols, and software tools. They
solve different problems: MQTT carries messages but does not define what a sensor
reading means. Verify coverage and the current specification when selecting an
implementation.

| Area | Examples to investigate | Planning implication |
| --- | --- | --- |
| Stage and lighting control | DMX512, Art-Net, sACN/E1.31, GDTF, MVR | Separate fixture/scene description from live transport and physical patching |
| Spatial audio | ADM/BWF, BW64 | Retain audio objects, channel layouts, and timed metadata separately from rendered channels |
| Notation and rehearsal | MusicXML, MEI, MIDI, SMuFL, LilyPond | Preserve notation meaning and engraving separately from performance playback |
| Robotics and kinetic work | ROS messages, rosbag, URDF, SDF, PLC and MQTT formats | Model safety limits and measured feedback before control delivery |
| Haptics | AHAP, Android haptic compositions, controller effects | Expect platform-specific adapters; no dominant interchange format exists |
| Environmental sensors | OGC SensorThings, SensorML, Observations and Measurements, NetCDF, CSV, MQTT | Preserve units, calibration, uncertainty, source time, and observation time |
| Interactive installations | OSC, MIDI, DMX, MQTT, WebSockets | Preserve raw traffic; project-specific event meaning needs an explicit adapter |
| Projection and spatial scenes | SVG, glTF, USD, MPCDI, vendor warp/blend formats | Keep geometry, still-image placement, and calibration distinct from endpoint delivery |
| Networked collaboration | Automerge, Yjs, operational transforms, JSON Patch | Treat ownership and conflict decisions as run or editing state, not implicit merges |
| Score following | MusicXML or MEI with MIDI/audio alignment data | No widely adopted interchange format represents live score position and confidence |
| Digital fabrication | G-code, STEP/STEP-NC, DXF, SVG, 3MF | Treat machine limits and material settings as binding-specific safety data |
| Accessibility | WebVTT, TTML/IMSC, EBU-TT, BRF | Caption interchange is mature; audio-description and sign-language cues are less standardized |

Possible candidates for structured import include ADM/BWF, MusicXML or MEI,
GDTF/MVR, glTF, SensorThings observations, and STEP/3MF. Each separates meaning
from at least some realization details. Formats with weak interchange should enter
first as sealed assets with a documented decoder or adapter, rather than forcing
their incomplete semantics into generic fields.

### References

- [Open Sound Control 1.0](https://opensoundcontrol.stanford.edu/spec-1_0.html)
- [GDTF and MVR overview](https://gdtf-share.com/help/)
- [ANSI E1.31 streaming ACN](https://tsp.esta.org/tsp/documents/docs/E1-31-2016.pdf)
- [Audio Definition Model usage guidance](https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-BS.2388-6-2025-TOC-HTM-E.htm)
- [glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
- [SMuFL](https://www.smufl.org/)
