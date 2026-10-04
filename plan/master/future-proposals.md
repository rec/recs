# Remaining cross-domain proposals

These are future applications and unresolved host/model extensions. Implemented
score schemas, codecs, and pure reference behavior belong to their owning
project's documentation. Use [the plan index](../README.md) for current owners;
these proposals do not authorize implementation.

## Suggested implementation order

| Step | Useful outcome | Existing foundation |
| --- | --- | --- |
| 1 | [Deliver controls and add richer quantities](#sampled-quantities-curves-and-physical-controls) | Scalar automation and time types |
| 2 | [Play editable actions through a host](#events-requests-and-sequences) | Sequence playback and raw event models |
| 3 | [Extend arrangement realization](#arrangements-sequences-and-nested-mixes) | Named parts, nested scores, event connections, and control clips |
| 4 | [Activate one real binding](#implementations-endpoints-and-parameter-mappings) | Binding schemas and parameter conversion |
| 5 | [Build a slideshow player](#live-slideshow-format) | Slideshow definitions and selection resolver |
| 6 | [Deliver fixture and pixel timelines](#fixture-controls-dmx-and-spatial-light-fields) | Fixture scores, layouts, patches, and existing drivers |
| 7 | [Run a broadcast and preserve what aired](#radio-programmes-live-sections-and-rebroadcast) | Broadcast definitions and run records |
| 8 | [Improve tools through use](#future-features-worth-building) | Experience with the earlier hosts |
| 9 | [Explore additional domains](#new-data-domains-and-interchange-formats) | A concrete need and representative data |

Each host should implement one useful profile before broadening its capabilities.
Shared-model changes belong in uFor; engine extensions belong in
[enge's roadmap](../../../enge/plan/roadmap.md). New playback and authoring hosts
belong outside recs. Existing definitions do not imply that a live player exists.

## Sampled quantities, curves, and physical controls

Remaining scope includes graph-wide ownership, editing tools, dense arrays,
physical CV delivery, richer quantities, and analysis-result streams.

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

### Remaining control integration

Graph-wide writer ownership, GUI editing, dense sampled arrays, and physical
delivery remain host or model extensions. Reuse the
[automation format](../../../ufor/doc/automation-format.md) for implemented
scalar curves, defaults, interpolation, and add/multiply contributions.

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

## Events, requests, and sequences

Host transport integration, MIDI-CI handling, SysEx reassembly/conversion, and
request execution remain later work. Reuse
[uFor's sequence playback specification](../../../ufor/doc/sequence-playback.md)
for implemented cropping, seeking, looping, note ownership, and end cleanup.
Raw captures remain inert until an explicit adapter interprets them.

### Raw capture and semantic editing

Preserve raw MIDI or OSC when fidelity to an unknown device matters. An editable
interpretation is a separate derived stream that records its mapping and the
source events it came from. Raw and semantic streams are related representations,
not two sets of commands to dispatch simultaneously.

MIDI adapters own channel/part mapping, overlapping-note matching, controller
resolution, sustain interpretation, and conversion to pitched performance. Keep
SysEx or other unrecognized messages as typed raw data. Export to a more limited
protocol reports quantization and unsupported per-note expression.

### MIDI and endpoint integration

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

## Arrangements, sequences, and nested mixes

Remaining extensions include logical gates, voice/instrument control scopes,
control combiners, tempo anchoring, audio speed changes, reversal, and host
audio/device execution. Reuse [uFor's arrangement
format](../../../ufor/doc/arrangement-format.md) and [automation
format](../../../ufor/doc/automation-format.md) for existing nested score and
control-clip behavior.

### Playback speed and tempo

A future clip-speed profile needs positive rational speed and exact timebase
conversion. For source interval `[a, b)`, timeline start `s`, and speed `r`,
source time `u` appears at `s + (u-a)/r`; duration is `(b-a)/r`. Specify final
sample-boundary rounding explicitly. Audio speed changes require a selected
resampling or time-stretch operation, with its pitch behavior explicit.

Musical clips may follow a parent tempo map when marked beat-anchored. A physical
recording stays in physical time unless explicitly warped. Reversal must be a
declared operation, not a negative speed applied to requests and note lifecycles.

Whole-program normalization remains an offline operation; a host cannot promise
it for unknown future live audio. Render caching and state checkpoints are
separate proposals below.

## Implementations, endpoints, and parameter mappings

The next host step is to preview a score and send it through one real adapter,
checking capabilities before output begins. Reuse the existing
[binding format](../../../ufor/doc/binding-format.md), parameter mappings, and
capability contracts. Adapter lookup, display/output selection, credentials,
and device/plugin activation remain host work. Select one concrete plugin host
for a first integration rather than adding every SDK.

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

Replace lyte's score-level Python `impl` resolution with adapter lookup at
preparation time. Move `DmxInstrument` patch fields, Twinkly connection fields,
and streamO device/service selection into binding responsibilities as each
application adopts the format. Reuse actual drivers and service adapters; do not
rewrite network transports to make the score model uniform.

showCo continues owning operational setup and service actions. uFor owns the
portable score model; hosts execute it through their selected bindings. Plugin hosting is a new implementation task, with a single concrete host
chosen for the first integration. The format proposal does not require adding
every plugin SDK as a dependency.

## Live slideshow format

Build a player using the existing
[slideshow format](../../../ufor/doc/slideshow-format.md) and selection resolver.
The first useful result is to resolve directories and exclusions, finish with two
explicit images, edit crops and timing, and replay a recorded manual presentation.
Include accessibility in that first usable player.

Remaining host work includes asset inspection/sealing, image/video decoding,
display selection, preview, cue delivery, caption rendering, and audio playback.
Reject unsupported transitions or decoders rather than substituting them.
Expose concise alt text at item entry and longer descriptions on demand.

Manual navigation must use the authored accompaniment policy. Captions follow
audible audio position; image descriptions follow the displayed item. Record
entered items, transitions, operator actions, delivered cues, caption
presentation, and display failures. As-presented replay follows those recorded
decisions; a fresh performance follows the definition and current binding.

Later proposals include additional ordering comparators, richer crops,
animation, multiple displays, live camera inputs, and new transition contracts.
General video editing and codec implementation remain outside this plan.

## Fixture controls, DMX, and spatial light fields

Use the existing [fixture format](../../../ufor/doc/fixture-format.md), layouts,
and patches with lyte's drivers. The first useful host result is to repatch a
fixture or rewire a pixel string without editing its cues, using the same
resolved values and layout for preview and delivery.

Remaining host work includes timeline delivery, preview integration, calibrated
device profiles, and measured output timing. Keep semantic fixture state,
spatial fields, and raw device traffic distinguishable. Bindings must explicitly
carry wire/display universe conventions, channel encodings, and calibration.

Multi-universe delivery needs a synchronization strategy and measured skew;
equal authored timestamps do not prove simultaneous physical presentation.
Device profiles own transfer curves, component order, RGBW conversion,
quantization, and power limiting. Normalized RGB is not evidence of linear color.

Sinks schedule at their supported refresh rate and report dropped updates.
Stop/disconnect applies the profile's blackout, fade, or held-state policy;
zero raw bytes are not a universal semantic off. Adapt existing show and
installation models as their applications adopt the common score, checking
their current implementation before changing drivers.

## Radio programmes, live sections, and rebroadcast

Build programme transport using the existing
[broadcast format](../../../ufor/doc/broadcast-format.md). Start with recorded
sections and one live input; add delayed relay and rolling buffers later.
Input connections, scheduling, playout, relay buffering, delivery, and capture
remain host work.

A delayed relay starts only after its required captured interval is available.
Offline preparation may render known sections and show unresolved live intervals,
but must label the result incomplete. Replaying a captured programme and running
its definition with new live material are distinct operator choices.

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

A programme host resolves and renders content and journals playout decisions.
recs records programme audio. streamO delivers a selected programme output and supplies supported live
feed adapters. showCo presents run readiness, timing, actionable failures, and
operator cues. lyte can consume synchronized programme controls through another
output. Scheduling is owned by one broadcast transport; applications must not
maintain competing copies of section position.

streamO should accept a programme's audio output through an explicit binding.
Service credentials and its other video features remain deployment settings. Its
existing delivery support does not itself provide a radio rundown model.

showCo's `ActionResult`, action log, and service status remain runtime views. They
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

A sample browser could create an instrument directly from selected recs
recording ranges, retaining the original take and edit provenance.

Timing humanization and authoring tools for seeded variations remain possible
extensions. Reuse existing seeded sample selection and pitch/gain variation;
keep authored randomness separate from the observed result of one performance.

Remaining [modulation extensions](deferred-work.md#envelopes-lfos-and-modulation)
include looped envelopes,
random/sample-and-hold sources, and continuous rate ramps remain later extensions
requiring their own conformance cases. Granular synthesis, convolution, time
stretching, and physical modeling are useful later processor capabilities. Prefer
binding an existing implementation when it meets the contract. Add a new universal
parameter only when its meaning across implementations can actually be stated.

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

## Additional work beyond the prompt

None.
