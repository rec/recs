# Recsam Instrument Format

## Status And Scope

Recsam is a proposed format, not an implemented playback feature or an existing
industry standard. It describes one playable instrument: the sample files,
which keys and velocities select them, and how each selected sample plays.

A UTF-8 TOML file named `sample-instrument.toml` holds the definition. Audio
stays in separate referenced files. One instrument can contain any number of
sample slots, including several slots referencing different parts of the same file.

Version 1 defines audio sampling. It does not assume that reversing MIDI
messages or applying EQ to OSC packets has the same meaning as processing
audio. Recs' session record remains the common container for all time-based
media; this document defines audio instrument behavior within that larger
system. Future media-specific playback semantics require a format revision,
not silently reinterpreting these audio fields.

The format is declarative. It cannot import Python, run shell commands, load
plugins, or depend on an installed sampler's opaque preset state. Clear names,
explicit units, and defined composition rules take precedence over matching
SFZ opcode names or syntax.

## Concepts

| Term | Meaning |
| --- | --- |
| Instrument | One playable definition containing sample slots and shared settings |
| Slot | A sample reference, key/velocity mapping, and local playback settings |
| Voice | One active playback instance of a slot, created by a trigger |
| Trigger | One performance onset with an explicit identity, selection key, and optional pitch |
| Part | A logical performance group, independent of transport channels |
| Control | A declared, named expression value in a normalized numeric domain |
| Frame | One simultaneous sample value per channel in an audio file |
| Mapping | Conditions under which a trigger selects a slot |
| Modulation | A numeric adjustment driven by trigger values, live controls, envelopes, or LFOs |
| Tag | An arbitrary text label with no playback effect |

Overlapping mappings layer unless their slots explicitly belong to an alternate
selection set. TOML order does not establish priority, and the last matching
slot does not win. A new Trigger creates new voices; it does not implicitly
replace existing ones.

## Complete Example

This instrument has a quiet and a loud velocity layer. Its overall volume
decreases toward the top of the keyboard. One slot additionally reduces its own high-key
volume and raises the frequency of its local EQ band. The other uses `mirror`.

```toml
format_version = 1

[instrument]
name = "Glass keys"
description = "Two velocity layers from a recorded glass instrument"
tags = ["glass", "pitched", "studio session"]

[instrument.playback]
direction = "forward"
mode = "while_held"

[instrument.envelope]
attack_seconds = 0.005
decay_seconds = 0.0
sustain_level = 1.0
release_seconds = 0.1

[instrument.processing]
volume_db = -3.0
tuning_cents = 0.0

[[instrument.processing.equalizer]]
id = "body"
frequency_hz = 700.0
gain_db = 1.5
resonance = 0.8

[[instrument.modulation]]
target = "volume_db"
input = "key"
operation = "add"
interpolation = "linear"
points = [
  { input = 0, amount = 0.0 },
  { input = 60, amount = -1.0 },
  { input = 120, amount = -6.0 },
]

[[instrument.modulation]]
target = "equalizer.body.gain_db"
input = "key"
operation = "add"
interpolation = "linear"
points = [
  { input = 0, amount = 0.0 },
  { input = 120, amount = -3.0 },
]

[[slots]]
id = "glass-soft"
name = "Soft strike"
sample = "audio/glass-soft.wav"
tags = ["soft", "clean attack"]

[slots.mapping]
lowest_key = 48
highest_key = 84
reference_pitch_hz = 261.6255653005986
minimum_velocity = 0.0
maximum_velocity = 0.625
pitch_tracking = true

[slots.playback]
start_frame = 0
end_frame = 96000

[slots.processing]
volume_db = -2.0
tuning_cents = 3.0

[[slots.processing.equalizer]]
id = "ring"
frequency_hz = 2400.0
gain_db = -4.0
resonance = 2.0

[[slots.modulation]]
target = "volume_db"
input = "key"
operation = "add"
interpolation = "linear"
points = [
  { input = 48, amount = 0.0 },
  { input = 84, amount = -2.0 },
]

[[slots.modulation]]
target = "equalizer.ring.frequency_hz"
input = "key"
operation = "multiply"
interpolation = "linear"
points = [
  { input = 48, amount = 0.5 },
  { input = 84, amount = 2.0 },
]

[[slots]]
id = "glass-hard"
name = "Hard strike, mirrored"
sample = "audio/glass-hard.wav"
tags = ["hard", "bright"]

[slots.mapping]
lowest_key = 48
highest_key = 84
reference_pitch_hz = 261.6255653005986
minimum_velocity = 0.625
maximum_velocity = 1.0
pitch_tracking = true

[slots.playback]
direction = "mirror"

[slots.processing]
volume_db = -5.0
```

## Performance Events And Input Bindings

A player consumes protocol-neutral events, not MIDI messages. Hosts translate
MIDI 1.0, MIDI 2.0, MPE, OSC, UI gestures, or sequencer actions into this common
representation. These are adapter responsibilities, not alternative instrument
schemas. Adapter configuration belongs to the host; no second instrument file
or embedded transport binding table is required.

Every event has a non-negative integer `frame` on the host's output-frame
timeline. Hosts convert external timestamps once and preserve supplied order
among events at the same frame. A logical `part` is an identifier, not a
restricted channel number.

| Event kind | Fields beyond `frame` |
| --- | --- |
| `trigger` | Required `part`, `trigger_id`, integer `key`; `velocity` defaults to 1.0; optional positive `pitch_hz`; optional `controls` mapping |
| `release` | Required `part` and `trigger_id` |
| `control_change` | Required `control`, `value`, and `scope`; target fields depend on scope |

`(part, trigger_id)` identifies one trigger instance. Several simultaneous
triggers can use the same key, with independent release and expression.
IDs must be unique while held or still owning live voices; a player rejects
reuse during that lifetime. A Release addresses that identity, never a FIFO
queue inferred from key numbers. It carries no new velocity: release samples
use the original trigger's velocity.

A Trigger's `controls` initializes only its trigger-scoped controls, using
declared defaults for omitted names. Velocity and controls retain floating-point
precision. Zero velocity is a valid Trigger, never an implicit Release.
The selection key does not determine pitch: the host supplies `pitch_hz`
when selecting pitch-tracked slots. Untracked triggers need no pitch.

A ControlChange's scope determines its target:

- `instrument`: no part or trigger ID.
- `part`: a part, but no trigger ID.
- `trigger`: both a part and a trigger ID.

Unknown control names or out-of-domain values are errors, including initial
Trigger controls. Polarity and defaults come from instrument declarations.
The player owns lifecycle state; declarations alone cannot determine whether
a trigger ID exists or whether a selected sample requires a target pitch.

MIDI-specific note-on-zero handling, channel/controller numbers, pitch-wheel
decoding, repeated-note matching, and MPE channel assignment belong in MIDI
adapters. OSC address/argument mappings belong in an OSC adapter. For example,
a host can map MIDI expression or an OSC path to the same named control;
neither transport's encoding becomes part of recsam's numeric domain.
Adapters must not reduce high-resolution inputs to seven-bit values.
No MIDI or OSC adapter, playback engine, or tuning system is implemented here.

## Structure And Defaults

The root contains exactly `format_version`, `instrument`, and `slots`. Version 1
requires `format_version = 1`, a nonempty `instrument.name`, and at least one slot.
Every slot requires a unique `id`, `sample`, and a `mapping` table containing
`lowest_key` and `highest_key`. Tracked slots also require `reference_pitch_hz`.

IDs use ASCII letters, digits, hyphens, and underscores. Names, descriptions,
and tags are Unicode text. An omitted slot `name` displays its ID. Descriptions
are optional on the instrument and on individual slots.

| Setting | Default |
| --- | --- |
| `tags` | `[]` at either scope |
| `mapping.minimum_velocity` / `maximum_velocity` | `0.0` / `1.0` |
| `mapping.pitch_tracking` | `true` |
| Instrument `playback.direction` | `"forward"` |
| Instrument `playback.mode` | `"while_held"` |
| Slot `playback.start_frame` | `0` |
| Slot `playback.end_frame` | Decoded file's frame count, exclusive |
| Slot `playback.loop` | Absent: no repetition |
| Instrument `selections` / slot `selection` | `[]` / absent: ordinary layering |
| Slot `choke_group` / `chokes` | Absent / `[]`: no choking |
| Slot `crossfades` | `[]`: unity layer weight |
| Slot `trigger` | `"start"` |
| Instrument `sustain` | Absent: no sustain control |
| Instrument `articulations` / slot `articulations` | Absent / `[]`: no restriction |
| Instrument `controls` | `{}`: no declared controls |
| `processing.volume_db` / `tuning_cents` | `0.0` independently at each scope |
| `processing.pan` / `stereo_balance` | `0.0` independently at each scope |
| `processing.equalizer` | `[]` independently at each scope |
| `modulation` | `[]` independently at each scope |
| `envelopes` / `lfos` | `[]` independently at each scope |
| Instrument `envelope.delay_seconds` / `hold_seconds` | `0.0` / `0.0` |
| Instrument `envelope.attack_seconds` / `decay_seconds` | `0.0` / `0.0` |
| Instrument `envelope.sustain_level` / `release_seconds` | `1.0` / `0.0` |
| Instrument `envelope.attack_shape` / `decay_shape` / `release_shape` | `"linear"` each |

Only playback direction, playback mode, and amplitude-envelope fields
inherit from the instrument. An absent slot override uses the
effective instrument value. The instrument cannot set trim boundaries because those refer
to particular files. Named envelopes and LFOs are independent declarations,
not inherited lists.

Processing and modulation are separate stages, not inherited defaults: missing
slot processing means an identity slot stage, followed by the instrument stage. It
does not mean copying the instrument stage and applying it twice. Spatial controls
combine into one final operation; amplitude-envelope duration curves apply
once to the inherited envelope, as specified in their respective sections.

## Sample References And Time

`sample` names one audio file, relative to `sample-instrument.toml`. References must
remain inside the instrument directory after path resolution, including symlink
resolution. Absolute paths, URLs, and paths escaping with `..` are invalid.
The instrument directory can be copied without changing its internal references.

The decoder provides channel count, native sample rate, and decoded frame
count. These are not duplicated as authoritative TOML fields. A player must
report an unsupported codec or channel layout, not silently drop a slot.

`start_frame` and `end_frame` select a half-open interval in the file's native
sample rate: `[start_frame, end_frame)`. They are non-negative integers, with
`start_frame < end_frame <= decoded_frame_count`. All channels share the same
boundaries and keep their file order. Compressed-file byte offsets have no
meaning here: these are decoded audio-frame positions.

Files with different native sample rates can share an instrument. Sampler playback
converts them to the output rate; that conversion does not alter the stored
trim positions. Timing never depends on filenames or filesystem timestamps.

## Key And Velocity Mapping

Keys are integer selection coordinates, with no MIDI-specific limits. Negative
keys and keys above 127 are valid. `lowest_key` and `highest_key` are inclusive
and ordered. A key identifies the region to play; it is not an encoded pitch
or a prescribed keyboard octave. Bindings may map pads, keyboard keys, OSC
messages, or algorithmic selectors onto these coordinates.

Velocity is a finite floating-point value in `[0, 1]`. Mapping bounds are
inclusive, default to zero and one, and must be ordered. Zero velocity is a
valid trigger, never a release command, and does not implicitly silence it.
Adjacent inclusive layers may both match their shared endpoint. The complete
example deliberately layers both samples at velocity 0.625; crossfades can
provide a smooth overlapping transition instead.

`pitch_tracking` defaults to true. A tracked slot requires positive finite
`mapping.reference_pitch_hz`, the sample's reference pitch, and a matching
performance trigger must supply positive finite `pitch_hz`. The base playback
ratio is `pitch_hz / reference_pitch_hz`. A missing target pitch is an error,
not permission to infer a twelve-tone pitch from the selection key.

With `pitch_tracking = false`, the base ratio is one and target pitch is ignored.
Instrument and slot tuning still apply. A reference pitch may remain as metadata
on an untracked sample. A host or tuning resolver supplies target frequencies;
scale definitions and microtonal mapping remain in the separate tuning spec.

`mapping.event_key` is required only on sustain-transition slots. It supplies
their selection coordinate because a control change has no key. Such slots
must be untracked and their key range must contain `event_key`. Other slots
must omit it. No fabricated pitch is attached to a sustain transition.

There is no hidden velocity-to-volume curve. Velocity selects layers and may
explicitly modulate volume. Selected overlapping slots sum without automatic
normalization. All voices from one trigger share an output-frame origin.
Version 1 specifies no implicit voice stealing.

## Alternate Sample Selection

Declare named selection sets on the instrument and associate each alternative slot
with one set. A selection set is not a shared processing group:

```toml
[[instrument.selections]]
id = "snare-takes"
mode = "cycle"

[[slots]]
id = "snare-a"
sample = "audio/snare-a.wav"
selection = "snare-takes"
[slots.mapping]
lowest_key = 38
highest_key = 38
pitch_tracking = false

[[slots]]
id = "snare-b"
sample = "audio/snare-b.wav"
selection = "snare-takes"
[slots.mapping]
lowest_key = 38
highest_key = 38
pitch_tracking = false
```

Set IDs are unique. Each requires `mode = "cycle"`, `"random"`, or `"shuffle"`;
there is no implicit choice. A slot may reference only one existing set. Slots
without `selection` continue to layer normally.

First evaluate mapping conditions. Partition eligible slots by selection set,
then choose exactly one eligible slot from each nonempty set. Empty sets make
no choice and do not advance state. Filter before selecting: differing velocity
layers or key ranges must not create silent holes in a sequence. Zero gain is
not a mapping exclusion.

- `cycle`: visit eligible slot IDs in ascending ASCII order, wrapping at the
  end. The initial choice is the first ID.
- `random`: choose uniformly among eligible slots on every trigger; immediate
  repetitions are allowed.
- `shuffle`: choose a uniform random permutation, consume it once, then refill.
  With at least two candidates, refills are uniformly chosen from permutations
  whose first slot differs from the previous choice. A single candidate always
  plays.

State is independent per set, part, trigger kind, trigger key, and
ordered tuple of eligible slot IDs. Velocity layers therefore have independent
sequences when their eligible IDs differ; changing velocity without changing
that tuple advances the same sequence. State advances once per selected set
per triggering event, not per audio block or active voice. Returning to a
previous eligible tuple resumes its state. Loading or explicitly resetting an
instrument clears all sequence state; ordinary release events do not reset it.

Cycle is fully deterministic. Random and shuffle define selection probabilities
but not cross-player seeded reproducibility; the separate reproducible-variation
proposal remains unimplemented. Do not claim that a seed alone guarantees
identical selection across engines.

Conformance cases cover layering outside sets, several independent sets,
candidate filtering before selection, one/zero eligible candidates, shuffle
refill boundaries, and invariance under audio block-size changes.

## Choke Groups

`slots.choke_group` labels voices created by that slot. Each `[[slots.chokes]]`
entry describes existing voices to stop when that slot is actually selected:

```toml
[[slots]]
id = "open-hat"
sample = "audio/open-hat.wav"
choke_group = "hats"
[slots.mapping]
lowest_key = 46
highest_key = 46
pitch_tracking = false
[slots.playback]
mode = "one_shot"

[[slots]]
id = "closed-hat"
sample = "audio/closed-hat.wav"
choke_group = "hats"
[slots.mapping]
lowest_key = 42
highest_key = 42
pitch_tracking = false
[slots.playback]
mode = "one_shot"
[[slots.chokes]]
group = "hats"
mode = "fade"
fade_seconds = 0.005
```

Choke groups are instrument-local IDs declared by membership, not processing groups
or selection sets. A slot belongs to at most one choke group and may choke
several groups. Every target must name a group used by at least one slot.
Membership alone does not cause mutual choking.

Each rule requires `group` and `mode`. Modes are `"immediate"` (stop before the
next output sample), `"fade"` (multiply the current output by a linear ramp
from one to zero), and `"release"` (enter the voice's release envelope).
`fade_seconds` is required, finite, and positive for fade, and forbidden for
the other modes. Release also applies to one-shot voices when explicitly
choked; it follows the loop's release policy. Fades and immediate stops create
no sample tail beyond the voice's existing material.

After all slots for one event have been selected, take a snapshot of existing
voices on that event's part. Apply selected slots' choke rules to that
snapshot, then create all new voices. Voices created by the same event never
choke one another. Later events at the same frame are processed in event-stream
order and can choke voices from earlier events.

The example's closed hat stops earlier open and closed hats, including older
instances of itself. Open-hat membership alone stops nothing. An unselected
alternate slot has no choke effect; a selected zero-gain slot still does.

Reject duplicate targets within one slot. If several selected slots target the
same voice, combine their termination gains by taking their minimum rather
than restarting or multiplying fades. An already-releasing envelope continues
from its current state; another choke never extends a voice's lifetime.
Choking is not a synthetic Release event and must not trigger release samples.

Conformance cases cover self-choking, layered event atomicity, part isolation,
unselected alternatives, already-releasing voices, and simultaneous rules.

## Layer Crossfades

Crossfades give overlapping layers complementary amplitude weights. They use
the same bounded curve evaluation as modulation, with a normalized position
instead of a separate arbitrary gain-automation language. These fragments go
in the respective existing slots:

```toml
# Soft slot: fades out as velocity increases.
[[slots.crossfades]]
input = "velocity"
direction = "out"
start = 0.4
end = 0.7
curve = "equal_power"
```

```toml
# Loud slot: complementary fade-in over the same interval.
[[slots.crossfades]]
input = "velocity"
direction = "in"
start = 0.4
end = 0.7
curve = "equal_power"
```

Each entry requires `input` (key/velocity or a live input defined below),
`direction` (`"in"` or `"out"`), and `start < end` in that input's valid
range. Key coordinates are integers; velocity and control coordinates are floats.
`curve` is `"linear"` (default) or `"equal_power"`. A slot may have one entry per
`(input, scope, control, direction)`, allowing a fade-in and fade-out on each
axis. Static key/velocity inputs have no scope or control field.

Clamp `t = (input_value - start) / (end - start)` to `[0, 1]`. Linear weights
are `t` for fade-in and `1 - t` for fade-out. Equal-power weights are
`sin(pi * t / 2)` and `cos(pi * t / 2)` respectively, with exact zero and one
at the endpoints. The opposing slots must use the same interval and curve to
be complementary. Their mapping ranges must both include the entire fade
interval for key/velocity inputs; a reader rejects a slot whose mapping cuts
off its nonzero transition. Live inputs do not widen or constrain key/velocity
mappings.

This example needs velocity mappings that overlap across the entire transition,
not just the shared endpoint in the complete instrument example. Crossfades neither widen mapping ranges nor
cause nonmatching slots to play. Matched slots with zero weight still create
voices and take part in selection and choking; silence is not a trigger filter.

Multiply all weights within a slot, then apply the result as a separate layer
gain alongside its envelope and volume before its EQ. Exact zero is silence,
not a fabricated finite dB value. Existing instrument and slot volume curves still
apply; neither replaces the crossfade. Key/velocity weights are captured at
trigger time; live-input weights follow the smoothing rules below.

Pairing is explicit through matching parameters, not inferred from neighboring
slots. With three or more overlapping layers, all their weighted signals sum
without normalization. Equal-power weights preserve the sum of squared gains
for a complementary pair, not constant peak level for correlated recordings.
Authors remain responsible for headroom.

Conformance cases cover exact endpoints, midpoint gain laws, simultaneous key
and velocity fades, zero-weight voices, clipped mapping ranges, and three-layer
overlaps. Alternate selection still chooses takes; it does not crossfade them
unless separate selected layers have crossfade settings.

## Named Articulations

Declare articulation IDs, a default, and optional key/control bindings:

```toml
[instrument.controls.style]
default = 0.0

[instrument.articulations]
ids = ["sustain", "plucked"]
default = "sustain"

[[instrument.articulations.keys]]
key = 24
articulation = "sustain"
behavior = "latched"
consume = true

[[instrument.articulations.keys]]
key = 25
articulation = "plucked"
behavior = "momentary"
consume = true

[[instrument.articulations.controls]]
control = "style"
minimum_value = 0.5
maximum_value = 1.0
articulation = "plucked"

[[slots]]
id = "pluck-middle"
sample = "audio/pluck.wav"
articulations = ["plucked"]
[slots.mapping]
lowest_key = 48
highest_key = 84
reference_pitch_hz = 261.6255653005986
```

The articulation table requires a nonempty, duplicate-free `ids` list and a
`default` naming one of them. Key and control binding arrays default to empty.
Slot articulation lists are duplicate-free references; an empty list means
eligible in every articulation. Tags remain descriptive.

Selection is independent per part. Key bindings have unique unrestricted
integer `key` values. `behavior` is `latched` (default) or `momentary`;
`consume` defaults to true. A latched trigger changes the persistent selection.
A momentary trigger overrides it until Release for that exact trigger ID.
The most recently started still-held momentary switch wins; latched changes
continue underneath it. Releasing the last momentary switch exposes the
latest persistent selection. Repeated keys do not require FIFO matching.

Switch releases are immediate, not deferred by sustain. A consumed switch
retains its trigger-ID ownership but creates no sample voices or release
samples. With `consume = false`, update articulation before selecting samples
for the same trigger; those voices retain their captured articulation.

A control binding names a declared control and an inclusive, ordered
`minimum_value`/`maximum_value` interval within its polarity's domain.
Intervals for the same control cannot overlap. Only part-scoped ControlChange
events drive these bindings. A match changes persistent selection; an
unmatched value leaves it unchanged. Bindings are latched and do not consume
the event: it may also affect sustain and modulation.

Selection affects future start and sustain-transition triggers, never remaps
existing voices. Release and logical-release samples use the original
trigger's captured articulation. Sustain samples use the part's current one.
Switching does not reset alternate-selection counters. Loading/resetting
restores defaults and clears held switch IDs without generating samples.
Control initialization does not execute bindings.

Conformance covers consumed/playable switches, exact-ID releases of repeated
keys, nested momentary switches, latched changes underneath them, independent
parts, control gaps, and captured articulation for release samples.

## Playback Direction

`direction` is exactly one of:

| Value | Traversal of the selected interval |
| --- | --- |
| `"forward"` | First selected frame to last selected frame |
| `"backward"` | Last selected frame to first selected frame |
| `"mirror"` | First to last, then back to first, once |

For selected frames `A B C D`, the traversal sequences at native rate and
original pitch are:

```text
forward:  A B C D
backward: D C B A
mirror:   A B C D C B A
```

The turning frame is not duplicated. For `N` selected frames, mirror traverses
`2 * N - 1` frames; a one-frame sample plays once in every direction. At other
pitch or output rates, resampling follows that traversal. Reversal affects
frame order, not channel order or sample polarity.

Mirror alone does not mean indefinite ping-pong looping. Without an explicit
loop, every direction eventually exhausts its selected material.

The instrument supplies the default direction. A slot's explicit direction replaces
that default, so a backward instrument plus a backward slot still plays backward,
not forward. Direction is not a numeric modulation target.

## Sustain Loops

A slot may add a loop inside its trimmed interval. Loop boundaries never inherit
from the instrument because they address one particular file. This fragment belongs
to an existing slot:

```toml
[slots.playback.loop]
start_frame = 24000
end_frame = 72000
mode = "until_release"
crossfade_frames = 256
```

Both boundaries are required native-frame integers. They define a half-open
interval inside the trimmed sample containing at least two frames. `mode` is
`"until_release"` (default) or `"through_release"`; `crossfade_frames` defaults
to zero. Loops require effective playback mode `while_held`, so a one-shot voice
cannot loop forever without a release event.

Forward playback enters from the trimmed start, then repeats the loop toward
increasing frames. Backward playback enters from the trimmed end, then repeats
it toward decreasing frames. Mirror enters from the trimmed start and reflects
between loop boundaries without repeating either turning frame. For loop
material `B C D`, its steady mirror sequence is `B C D C B C D ...`.

On release, `until_release` disables future wrapping and reflection immediately.
Playback continues in its current direction toward that trimmed sample boundary
while the release envelope runs. It does not jump to the tail. If a boundary
and release coincide, process release before the boundary transition.
`through_release` keeps repeating until the release envelope reaches zero;
it does not subsequently play a tail. Exhaustion or envelope completion,
whichever comes first, ends the voice. If release occurs before loop entry,
`until_release` never enters repetition.

For forward or backward wrapping, a positive crossfade overlaps the final `M`
frames of the traversal with the first `M` frames of its next traversal. Require
`M >= 2` and `2 * M < loop_length`. At overlap position `j`, use incoming weight
`j / (M - 1)` and outgoing weight `1 - j / (M - 1)`. After the overlap, resume
at frame `M` of the next traversal, not at its already-consumed first frame.
Thus the repeat period is `loop_length - M` native frames. All channels use the
same weights; fractional playback positions interpolate this traversal.

If release disables repetition during an overlap, finish that overlap and then
continue from the incoming head without further wrapping. Mirror requires
`crossfade_frames = 0`: its reflection already joins adjacent frames, and this
version does not define a separate turn-smoothing algorithm.

Conformance cases cover forward/backward wrapping, mirror endpoint order,
crossfade duration and head consumption, release before entry, release during
an overlap, and both release modes. The no-loop direction examples remain
unchanged.

## Release And Sustain Samples

Each slot's `trigger` is `start` (default), `release`, `logical_release`,
`sustain_press`, or `sustain_release`. Release means the explicit input event;
logical release means the eventual release after sustain deferral.

```toml
[instrument.controls.sustain]
default = 0.0

[instrument.sustain]
control = "sustain"
threshold = 0.5

[[slots]]
id = "key-tail"
sample = "audio/key-tail.wav"
trigger = "logical_release"
[slots.mapping]
lowest_key = 48
highest_key = 84
reference_pitch_hz = 261.6255653005986
[slots.playback]
mode = "one_shot"

[[slots]]
id = "sustain-up"
sample = "audio/sustain-up.wav"
trigger = "sustain_release"
[slots.mapping]
lowest_key = 60
highest_key = 60
event_key = 60
pitch_tracking = false
[slots.playback]
mode = "one_shot"
```

Sustain is absent by default. When present it requires a declared unipolar
`control` and a finite threshold in `(0, 1]`, default 0.5. State is per part,
initially derived from the control's default. Only part-scoped changes to that
control affect sustain. Values at or above threshold mean pressed; only
threshold crossings generate sustain-transition samples. Sustain slots are
invalid without a sustain declaration. No control name has hidden semantics.

A Trigger creates an instance identified by `(part, trigger_id)`, owning its
voices, original key, velocity, target pitch, articulation, and trigger-scoped
controls. The host must not reuse this identity while it is held or owns live
voices, including release voices. Repeated keys have distinct IDs and may be
released in any order. Retain ownership of held triggers even after their
audio exhausts. Ignore unknown or already-released Release events.

On the first matched Release, generate `release` once if at least one original
start voice is active and neither released nor choked. If sustain is off,
generate `logical_release` under the same condition and release owned
while-held voices. Otherwise defer logical release until sustain goes off.
Recheck original-voice eligibility then: exhausted/choked triggers generate
no release samples. Sustain never resurrects a voice or interrupts a release
already underway.

Release samples use the original key, velocity, target pitch, and articulation,
not values inferred from the release event. They share their owning trigger's
live controls. Selection happens once per trigger instance, not once per layer.
Release and sustain samples require one-shot playback without loops; they
cannot recursively generate releases. Chokes are not input Release events.

Sustain samples use their own `event_key` and the current control value as
velocity, including zero on release. They have no owning performance trigger:
trigger-scoped routes use control defaults and cannot be addressed later.
Within one selection set and sustain-trigger kind, alternatives must share
`event_key` so they participate in the same selection decision.

On sustain release, update state, process pending triggers in their start
order, and generate sustain-release samples. All voices derived from one
input event form an atomic batch; select them before applying chokes to
previous voices. Later events at the same frame retain input order.
Reset clears held/deferred IDs and restores control-derived sustain state
without generating release or sustain samples.

Conformance covers out-of-order releases of repeated keys, zero-velocity
starts and sustain releases, independent parts, sustain deferral, exhausted
voices, ignored duplicate releases, and nonrecursive tails.

## Release And Envelope

Playback `mode` is `"while_held"` or `"one_shot"`:

- `while_held`: logical release starts the matching voices' release stage;
  a declared sustain control can defer it after an explicit Release event.
- `one_shot`: release event does not shorten playback; the traversal runs to its end.

In either mode, a voice ends when its traversal is exhausted. Only an explicit
sustain loop repeats material; exhaustion manufactures no additional tail.
In one-shot mode, ordinary release events do not apply `release_seconds`; an explicit
release choke may do so. Trigger-instance ownership follows the release rules
above.

The amplitude envelope has delay, attack, hold, decay, sustain, and release
stages. It stays at zero for `delay_seconds`, rises to one during
`attack_seconds`, stays at one for `hold_seconds`, falls to `sustain_level`
during `decay_seconds`, then holds that level until release. The sample
traversal continues during delay; this is not a delayed sample start.

When release starts, skip any remaining delay/attack/hold/decay and proceed
from the current level to zero over `release_seconds`. Sustain-control deferral
and explicit release chokes apply as above. Times are finite non-negative
seconds measured in output time, independent of pitch and direction.
`sustain_level` is in `[0, 1]`.

`attack_shape`, `decay_shape`, and `release_shape` each accept `"linear"`
(default) or `"exponential"`. For stage progress `t` in `[0, 1]`, define
`f(t) = t` for linear or `f(t) = (exp(5*t) - 1) / (exp(5) - 1)` for
exponential. Attack produces `f(t)`; decay produces
`sustain_level + (1 - sustain_level) * f(1-t)`; release produces
`release_start_level * f(1-t)`. Endpoints are exact, including zero.

Each timed stage lasts `ceil(seconds * output_rate)` frames. Its start is
progress zero; its end is progress one and also the next stage's start.
Zero-duration stages transition immediately, including at voice creation.
An event at a stage boundary takes effect before rendering that frame; release
captures the envelope's value at that instant. Repeated releases do not restart
or prolong a release. Completing amplitude release ends the voice even if a
modulation envelope still has time remaining.

Instrument envelope fields supply defaults. Slot fields override individual defaults
before voice creation. There is one effective amplitude envelope per voice,
not two multiplied amplitude envelopes. Its duration may outlast the available traversal;
the voice still ends at exhaustion.

### Key-Dependent Envelope Timing

Static key/velocity curves can multiply `envelope.delay_seconds`,
`envelope.attack_seconds`, `envelope.hold_seconds`, `envelope.decay_seconds`,
and `envelope.release_seconds`. For example, higher keys can decay faster:

```toml
[instrument.envelope]
decay_seconds = 1.0
sustain_level = 0.4

[[instrument.modulation]]
target = "envelope.decay_seconds"
input = "key"
operation = "multiply"
points = [{ input = 48, amount = 2.0 }, { input = 84, amount = 0.5 }]
```

Resolve instrument defaults and slot overrides first, then multiply by all applicable
instrument and slot timing-curve amounts once. A slot override changes the base
duration, not whether the instrument curve applies. Capture durations at voice
creation, including release duration. Zero remains zero; ratios must be
positive. Live or generated inputs cannot target envelope settings, so a
changing control cannot retroactively change a stage boundary.

## Modulation Envelopes And LFOs

Declare named sources with `[[instrument.envelopes]]`, `[[slots.envelopes]]`,
`[[instrument.lfos]]`, or `[[slots.lfos]]`. Each requires an `id`, unique across
envelopes and LFOs in that declaring scope. Instrument and slot IDs are independent.
Routes reference a source in their own declaring scope, never an arbitrary
path into another slot. An instrument declaration applies to every selected voice;
it does not replace a slot declaration with the same ID.

```toml
[[instrument.envelopes]]
id = "pitch-fall"
attack_seconds = 0.0
decay_seconds = 0.2
sustain_level = 0.0
release_seconds = 0.05

[[instrument.modulation]]
target = "tuning_cents"
input = "envelope"
source = "pitch-fall"
operation = "add"
points = [{ input = 0.0, amount = 0.0 }, { input = 1.0, amount = 120.0 }]

[[instrument.lfos]]
id = "vibrato"
scope = "voice"
waveform = "sine"
frequency_hz = 5.0
delay_seconds = 0.15
phase_cycles = 0.0

[[instrument.modulation]]
target = "tuning_cents"
input = "lfo"
source = "vibrato"
operation = "add"
points = [{ input = -1.0, amount = -15.0 }, { input = 1.0, amount = 15.0 }]
```

### Envelope Sources

Named envelopes reuse the amplitude envelope's fields, defaults, stage shapes,
and frame timing, but do not inherit the instrument amplitude-envelope values.
Their output lies in `[0, 1]`. Each voice owns a fresh instance, including
voices triggered by release or sustain samples. They follow that voice's logical
release or release choke, not a second independent release event policy. One-shot
voices ignore ordinary release events for all their envelopes.

Finishing a modulation envelope leaves its output at zero; it does not end the
voice. Conversely, a voice's end discards all its per-voice sources. An envelope
is still evaluated while its voice has zero amplitude or crossfade weight.
There are no instrument-clock envelopes: an instrument-declared envelope is per voice.

Static timing curves may target `envelopes.ID.FIELD`, where `FIELD` is one of
the five duration fields allowed on the amplitude envelope. The ID must name
an envelope in the curve's own scope. These curves affect only that source's
duration, captured from each voice's trigger context; they do not target the
amplitude envelope or other sources with the same ID.

### LFO Sources

An LFO requires finite positive `frequency_hz`. Optional fields are `scope`
(`"voice"` by default, or `"instrument"`), `waveform` (`"sine"` by default or
`"triangle"`), non-negative `delay_seconds` (default zero), and
`phase_cycles` in `[0, 1)` (default zero). Slot LFOs require voice scope.
Frequency must be below half the output sample rate.

For output rate `R`, set `D = ceil(delay_seconds * R)`. At elapsed frame
`n >= D`, phase is `p = (phase_cycles + (n-D)*frequency_hz/R) modulo 1`.
Sine produces `sin(2*pi*p)`. Triangle produces `1 - 4*abs(p - 0.5)`.
Both have range `[-1, 1]`; phase and waveform therefore fully determine the
initial value. Before frame `D`, routes from this LFO contribute the neutral
amount (zero for add, one for multiply), rather than evaluating a point curve
at a fabricated LFO value. The oscillator starts at its configured phase at
`D`; there is no implicit fade-in.

A voice LFO's frame zero is voice creation. Every retrigger, including a
release/sustain voice, starts a fresh oscillator. An instrument LFO's frame zero is
instrument activation or explicit reset on the host output timeline; it advances
even with no voices and is shared across parts. A new voice joins its
current phase and delay state, never resets it. A voice LFO runs through
amplitude release until its voice ends; an instrument LFO runs until instrument deactivation
or reset. No tempo synchronization or trigger-driven reset of an instrument LFO is implied.

### Routing And Composition

Use the existing modulation array with `input = "envelope"` or `"lfo"` and
required `source`. `source` is forbidden on other inputs. Source kind must
match `input`. Generated routes have no `scope`, `control`, or
`smoothing_seconds`: scope belongs to the source and values are evaluated at
every output frame. Their point inputs may be fractional, in `[0, 1]` for
envelopes or `[-1, 1]` for LFOs. Existing interpolation and endpoint rules apply.

Point amounts supply modulation depth in the target's units. Generated routes
use the same processing targets and composition as other curves, including
EQ and spatial controls, but cannot target envelope settings, LFO parameters,
or another route's depth. This is not a recursive modulation graph. Multiple
sources targeting one parameter add their amounts or multiply their ratios
without declaration-order priority. All source ranges and simultaneous
contributions are included in load-time validation.

Conformance cases cover all envelope stages and zero-duration boundaries,
release during each stage, sustain-deferred release, exponential endpoints,
instrument-default/slot-override timing curves, named-source isolation, per-voice
retriggering, shared phase across parts and silent intervals, delayed LFO
neutral amounts, and identical trajectories for different render block sizes.

## Instrument And Slot Processing

Both scopes have the same `processing` table and `modulation` array. Instrument
settings apply to every triggered voice, including voices whose slots contain
their own processing. Slots cannot bypass the instrument processing stage.

`volume_db` is amplitude gain in decibels. Zero is unity; negative values
attenuate. The multiplier is `10 ** (volume_db / 20)`. Instrument and slot volume add
in dB, so instrument `-3.0` and slot `-2.0` produce `-5.0` before any modulation.

`tuning_cents` is an additional pitch adjustment. One hundred cents is one
semitone. Effective instrument and slot tuning add, and the total playback multiplier
is:

```text
base_ratio = pitch_hz / reference_pitch_hz if pitch_tracking else 1
pitch_ratio = base_ratio * 2 ** ((instrument_cents + slot_cents) / 1200)
```

Named pitch-bend routes contribute to instrument or slot tuning like any other
modulation curve. Higher pitch shortens a traversal; this is
sampling by playback-rate change, not time stretching. Sample-rate conversion
additionally uses the native rate relative to the host's output rate.

### Panning And Stereo Balance

`processing.pan` positions a mono sample in stereo: `-1` is left, `0` center,
and `1` right. `processing.stereo_balance` balances an already-stereo sample
over the same range, without collapsing or swapping its recorded channels.
These are separate operations, not two names for the same effect.

```toml
# In a mono slot:
[slots.processing]
pan = -0.5
```

Both default to zero. Their modulation operation is `add`. Add the instrument and
slot values, including their respective modulation contributions, to obtain
one effective pan or balance per voice. Validate the combined range within
`[-1, 1]`; do not silently clamp. Apply the spatial operation exactly once,
after both EQ stages and before summing voices. Unlike volume and EQ, instrument
and slot spatial settings are not two successive processors.

For mono value `x` and effective pan `p`, emit
`left = x*cos(pi*(p+1)/4)` and `right = x*sin(pi*(p+1)/4)`.
Use exact zero/one at the extremes. Center sends `x/sqrt(2)` to each side;
this is equal-power panning, not unity gain in both channels.

For stereo balance `b >= 0`, multiply left by `cos(pi*b/2)` and leave right
unchanged. For `b <= 0`, leave left unchanged and multiply right by
`cos(pi*(-b)/2)`. Center is the unchanged stereo sample. An extreme mutes the
opposite channel; it does not fold it into the remaining channel.

Pan applies only to mono samples; balance only to stereo samples. A nonzero
base value or any route to an inapplicable control is invalid. For example,
instrument-wide pan modulation requires all slots to be mono; mixed mono/stereo
instruments place such routes on the appropriate slots. Multichannel samples beyond
stereo cannot use either control. A nonzero spatial base value or any spatial
route requires stereo host output. Otherwise existing host channel-layout
rules apply; there is no implicit downmix. In a stereo host, mono voices use
the center pan law even when no pan field is written. On a mono host, a mono
voice without spatial settings passes through without the center-pan gain
reduction. Explicit zero values behave the same as omitted defaults.

Conformance cases cover mono center and extremes, unchanged stereo center,
one-sided balance without fold-down, combined instrument/slot offsets, live/LFO
motion, wrong sample layouts, and rejection on non-stereo hosts.

### Equalizer

Each `[[instrument.processing.equalizer]]` or `[[slots.processing.equalizer]]` entry
defines one bell-shaped parametric EQ band:

| Field | Meaning |
| --- | --- |
| `id` | Required unique band ID within that processing scope |
| `frequency_hz` | Required center frequency, greater than zero |
| `gain_db` | Required center-frequency boost or cut; zero is neutral |
| `resonance` | Required positive, dimensionless Q value; larger values give narrower bands |

Version 1 specifies a digital peaking biquad using the coefficient convention
in the [W3C Audio EQ Cookbook](https://www.w3.org/TR/audio-eq-cookbook/).
For effective frequency `f`, gain `g`, resonance `Q`, and host output
sample rate `R`, define:

```text
A = 10 ** (g / 40)
w = 2 * pi * f / R
alpha = sin(w) / (2 * Q)
b0 = 1 + alpha * A       a0 = 1 + alpha / A
b1 = -2 * cos(w)         a1 = -2 * cos(w)
b2 = 1 - alpha * A       a2 = 1 - alpha / A
```

Normalize all coefficients by `a0`, then use the transfer function
`(b0 + b1*z^-1 + b2*z^-2) / (1 + a1*z^-1 + a2*z^-2)`. Effective frequency must
be strictly below half the output rate. Bands process each channel separately
with independent filter state, initialized to zero for each voice.

Bands run in listed order. Slot bands run before instrument bands; lists concatenate
in the signal path rather than replacing each other. A band ID is local to its
scope: a slot band named `body` does not override an instrument band named `body`.

### Signal Order

For each incoming performance event:

1. Update named-control, articulation, sustain, and trigger-instance state and
   derive trigger contexts. Filter slots by trigger kind, articulation, and mapping, then
   select alternatives while retaining ordinary layers. Apply their choke rules
   to existing voices before creating the selected voices.
2. Resolve playback and envelope defaults, capture static curves,
   and initialize live modulation/crossfade state from current controls.
   Create per-voice envelopes/LFOs and attach routes to shared instrument LFOs.
   Before rendering each frame, evaluate sources and compose their amounts
   with static curves and smoothed live contributions.
3. Traverse the trimmed frames and optional loop in the effective direction,
   then resample for pitch.
4. Apply the effective amplitude envelope, crossfade weight, and slot volume,
   then slot EQ bands.
5. Apply instrument volume, then instrument EQ bands, independently to each voice.
6. Apply the combined pan or stereo balance once, then sum voices in the host's
   output channel layout without implicit downmixing.

Instrument processing is conceptually per voice, not a single post-mix effect. This
is necessary because two simultaneously held notes may require different instrument
EQ settings. A player may optimize equivalent calculations without changing
the result.

Processing uses floating-point headroom without implicit clipping or
normalization between stages. Final device limiting or file-encoding clipping
is a host/output policy, not a hidden instrument operation. Interpolation and numeric
precision may differ between players; version 1 does not promise bit-identical
audio from every implementation.

## Scaling Across Keys And Velocities

`[[instrument.modulation]]` affects the entire instrument. `[[slots.modulation]]` affects
only its containing slot. Both use the same fields:

| Field | Meaning |
| --- | --- |
| `target` | Numeric processing parameter or permitted envelope duration |
| `input` | `"key"`, `"velocity"`, `"control"`, `"envelope"`, or `"lfo"` |
| `source` | Required local source ID for envelope/LFO input only |
| `scope` | Live input scope; see Named Controls And Live Modulation; absent on static/generated curves |
| `control` | Required declared control ID for control input only |
| `smoothing_seconds` | Live-input transition time, default `0.005`; absent on static/generated curves |
| `operation` | `"add"` or `"multiply"` |
| `interpolation` | `"linear"` or `"step"`; default `"linear"` |
| `points` | Nonempty list of `{ input = number, amount = number }` points; key inputs require integers |

Supported processing targets are `volume_db`, `tuning_cents`, `pan`,
`stereo_balance`, and
`equalizer.BAND_ID.frequency_hz`, `equalizer.BAND_ID.gain_db`, or
`equalizer.BAND_ID.resonance`. Band IDs must name an existing band in the
same scope. A slot curve cannot reach into the instrument to disable its processing.

Modulation for `volume_db`, `tuning_cents`, `pan`, `stereo_balance`, and EQ
`gain_db` uses `add`; its amount is in the target's units. Frequency and resonance use
`multiply`; amounts are positive dimensionless ratios. Static key/velocity
curves may also multiply the envelope duration targets defined above. Other
target/operation combinations are invalid.
This prevents, for example, accidentally multiplying a negative dB value when
the intention was to double the amplitude.

Points have strictly increasing inputs. Keys are unrestricted integers; velocity
uses `[0, 1]`. Controls use their declared polarity's range. Generated inputs
use their source's numeric range as specified above.
A single point defines a constant adjustment.
Linear interpolation operates on the numeric amounts between adjacent points.
Step interpolation holds the left point until the next point's input. At an
exact point, use that point's amount. Outside the listed range, hold the nearest
endpoint; do not extrapolate.

Key coordinates are absolute values, not a percentage of occupied keys or of
the slot's mapped range. Adding or removing a slot cannot change an instrument curve's
meaning. Curves apply to supported sample layouts, subject to the spatial
controls' mono/stereo restrictions.

At most one curve may exist per `(target, input, scope, control, source)`
in each processing stage, treating absent fields as absent in this key.
Static inputs have no scope/control/source; generated inputs have only
source. If several inputs affect one target, add their amounts to its base
value, or multiply their ratios by its base value, according to the target's
permitted operation.
Array order has no effect on that combination. Instrument and slot scopes are then
combined using the processing rules above.

Key and velocity curves are evaluated from the trigger context and held for
the voice's lifetime. Named-control curves can change throughout
playback as described below. Generated sources evolve at output-frame precision;
envelope timing curves remain fixed for each voice's lifetime.

For example, at key 60 the example's instrument volume is `-3 + -1 = -4 dB`.
The soft slot's key curve is `-2/3 dB` there, so its slot volume is
`-2 - 2/3 dB`. Its combined volume is `-6 2/3 dB`, before envelope and EQ.
The instrument's EQ gain curve and that slot's EQ frequency curve are both applied;
neither replaces the other.

## Named Controls And Live Modulation

Declare controls once on the instrument. IDs follow the normal identifier
syntax; there are no controller numbers, implicit pressure controls, or
built-in MIDI bindings. Each definition contains `polarity` (`unipolar` by
default or `bipolar`) and `default` (zero by default). Unipolar values are
finite floats in `[0, 1]`; bipolar values are in `[-1, 1]`. Defaults,
events, selector intervals, and curve coordinates must fit that domain.

```toml
[instrument.controls.expression]
default = 1.0

[[instrument.modulation]]
target = "volume_db"
input = "control"
control = "expression"
scope = "part"
operation = "add"
smoothing_seconds = 0.01
points = [
  { input = 0.0, amount = -60.0 },
  { input = 1.0, amount = 0.0 },
]
```

Live routes require `input = "control"` and a declared `control` ID.
Their `scope` is `part` (default), `instrument`, or `trigger`, and
`smoothing_seconds` defaults to 0.005. These fields are forbidden on static
and generated routes. There are no separate controller or pressure variants:
pressure is simply a declared unipolar control routed to the desired target.

Each scope owns independent state initialized from declared defaults:

- Instrument: one value shared by all parts and voices.
- Part: one value for each logical performance part, shared by its voices.
- Trigger: one value for each trigger instance and its owned start/release
  voices, initialized by defaults plus that Trigger's `controls` values.

Scopes do not cascade. Updating an instrument control does not write part or
trigger state. A route reads only its specified scope. Trigger-scoped values
address exact IDs, not all voices with a matching key. An unknown trigger
control update is ignored after validating the control name/value; it is not
saved for a future trigger that happens to reuse that ID. Sustain samples
without a trigger owner read trigger defaults. Instrument processing remains
per voice even when its route reads part- or trigger-scoped input.

### Pitch Bend And Pressure

Pitch bend is an ordinary named bipolar control routed to `tuning_cents`:

```toml
[instrument.controls.bend]
polarity = "bipolar"
default = 0.0

[[instrument.modulation]]
input = "control"
control = "bend"
scope = "part"
target = "tuning_cents"
operation = "add"
smoothing_seconds = 0.005
points = [
  { input = -1.0, amount = -200.0 },
  { input = 1.0, amount = 200.0 },
]
```

This explicitly supplies a two-semitone range; other amounts provide different
or asymmetric ranges. Trigger scope supplies independent per-trigger bend.
Slot routes permit different ranges by slot. There is no `pitch_bend` settings
table or implicit pitch adjustment in addition to these routes. Instrument
and slot contributions still add. Untracked samples can be bent explicitly;
omitting a route means no bend.

Pressure uses the same syntax, for example `control = "pressure"`, declared
unipolar with default zero. Part-wide and per-trigger pressure are scopes,
not separate input types. Neither control changes sample selection, key,
the captured target pitch, the sample's reference pitch, source phase, or
envelope timing.

### Live Curve Timing

For each existing voice, an event supplies a new curve amount. Ramp linearly
from its current amount to that new amount over
`N = ceil(smoothing_seconds * output_rate)` output frames. On frame `j`, counting
the event frame as `j = 1`, use `old + (new - old) * j / N`, reaching the target
on the final frame. Zero seconds applies
immediately. A new event during a ramp starts from the current interpolated
amount rather than restarting from the old target. The time must be finite and
non-negative. Each contribution is smoothed before composing it with other
contributions. Newly created voices initialize directly from current input
values; they do not sweep from reset values.

Apply parameter changes at their scheduled output frames, not merely at block
boundaries. For changing EQ parameters, recompute the specified coefficients
from effective parameters while preserving the voice's filter state. Do not
reset filters or interpolate arbitrarily between coefficient sets. Changing
tuning changes traversal speed without resetting playback position, direction,
loop phase, or envelope time. No normalization is introduced.

### Live Layer Balance

Crossfades accept the same named controls, scopes, and smoothing
times. Two overlapping slots can use these complementary fragments:

```toml
[instrument.controls.layer_balance]
default = 0.0

[[slots.crossfades]]
input = "control"
control = "layer_balance"
scope = "part"
direction = "out"
start = 0.0
end = 1.0
curve = "equal_power"
smoothing_seconds = 0.01
```

The other slot uses the same values with `direction = "in"`. For crossfades,
smooth the normalized position `t`, then compute the gain law. Matching times
and intervals therefore keep complementary pairs complementary throughout a
transition. Do not smooth their sine/cosine gains independently. Initialize new
voices at the current unsmoothed target position, as with ordinary live curves;
only equally initialized paired voices have that complementarity guarantee.

Control updates change existing voices' gains but do not create or reselect
slots. Both layers must be selected at trigger time, including a layer whose
initial weight is zero. A layer that has exhausted its sample cannot be
resurrected by changing a control. Articulation switches remain future-trigger
selectors, not live crossfades.

### Reset And Validation

Explicit instrument reset stops voices, clears trigger/selection/switch state and
ramps, restores declared control defaults independently in each scope and default
articulations, and restarts instrument LFO clocks at frame zero. It generates no
release samples. New voices thereafter use that initial state. Do not equate
arbitrary incoming control changes with an instrument reset unless their behavior
is explicitly specified.

Validate effective parameters across all applicable static, live, and generated
inputs, including simultaneous contributions and smoothing trajectories. Positive
frequency/resonance multipliers must remain positive; effective EQ frequencies must
remain below Nyquist. A player must reject unsafe combinations at load time,
not silently clamp modulation during playback. Conservative interval analysis
is acceptable if it reports the rejected parameter and range clearly.

Conformance cases cover configured initial values, part/instrument/trigger scopes,
independent expression on repeated keys, overlapping ramps, mid-block updates, state-preserving
EQ changes, paired live fades, exhausted layers, and reset without spurious
triggers. Replaying identical events with different block sizes must produce
the same parameter trajectories.

## Tags

`instrument.tags` and each slot's `tags` are independent lists of zero or more
nonempty text strings. Spaces and Unicode are allowed. Tags are case-sensitive;
readers must not split a tag on spaces, normalize its spelling, or interpret
punctuation as hierarchy. An omitted list is the same as `[]`.

Duplicates within one list are invalid. An instrument and a slot may share the same
tag. Written order is preserved for display but has no semantic meaning.

Instrument tags describe the instrument as a whole; slot tags describe individual
samples or mappings. Instrument tags are not copied into slot lists. A UI may offer
combined searching, but must retain their distinct scopes. Tags never select
notes, change volume, or secretly enable articulations.

## Relationship To Recs Sessions And Edits

A standalone instrument needs only `sample-instrument.toml` and its referenced audio files.
An instrument generated by a Recs edit lives in the edit's new output session:

```text
glass-instrument/
  session-record.jsonl
  edit.toml
  sample-instrument.toml
  audio/
    glass-soft.wav
    glass-hard.wav
```

These are three different metadata artifacts, not three copies of one schema:

- `session-record.jsonl` indexes generated media and records lifecycle and
  provenance, following [Session Record Format](session-record-format.md).
- `edit.toml` preserves the resolved transformation that produced the result,
  as specified in the existing editing plan.
- `sample-instrument.toml` describes how the result responds to future performance
  events. It does not duplicate edit history or source-session selectors.

The instrument references the generated audio files directly, not an input session's
files. Its playback requires neither input sessions nor the edit recipe. A
player does not execute `edit.toml` when loading an instrument.

The output session records the generated audio normally. The instrument definition's
relative path may be identified in lifecycle metadata; it is not disguised as
an audio file or embedded as sample quantity data. Producing an instrument from a
mixed-media session does not implicitly copy MIDI, OSC, or other unsupported
media into the output.

## Validation And Portability

A reader validates the complete instrument before accepting it for playback:

- Recognized format version, field names, and enum values; no unknown values
  silently ignored and no evaluation of embedded code.
- Required fields, unique slot IDs, local EQ IDs, and nonempty names/tags.
- Unique selection-set IDs, valid selection modes, and existing set references.
- Existing choke-group targets, unique per-slot targets, and valid choke modes
  and fade times.
- Crossfade input ranges, unique input/scope/control/direction keys, gain
  curves, and mappings covering each static crossfade transition.
- Trigger kinds, sustain settings, one-shot release/sustain playback, and untracked
  sustain mappings containing their declared event key.
- Declared articulation references and default, unique keyswitch keys, and
  nonoverlapping named-control selector ranges.
- Key/velocity bounds, trim intervals, existing contained audio files, and
  supported decoding and output channel layouts.
- Contained loop intervals, valid loop/playback-mode combinations, and permitted
  crossfade lengths and directions.
- Finite numeric values, positive frequencies and resonance, non-negative envelope
  times, valid envelope shapes and sustain levels.
- Unique local envelope/LFO IDs, matching source references, valid source
  scopes, waveform/phase/frequency ranges, and permitted static duration targets.
- Pan/balance sample-layout and stereo-output requirements, and combined
  spatial ranges within `[-1, 1]`.
- Existing modulation targets, permitted operations, ordered point inputs,
  and positive multiplicative amounts.
- Declared control IDs, polarity domains, defaults, live scopes, and smoothing times.
- Valid effective parameters over every static/live/generated input combination
  that can affect each slot, including instrument and slot curves. Validation uses
  the host output rate for EQ/LFO frequency limits and is repeated if that rate
  changes.

Errors identify the slot, band, or curve and the offending field. A player that
cannot support a declared feature must reject the instrument with an explanation,
not silently skip the feature and claim to have loaded it faithfully.

Useful conformance cases include layered velocity mappings; independent instrument
and slot volume curves; instrument and slot EQ with identical local band IDs; all
three directions for one-, two-, and four-frame traversal definitions; release event
in each mode; empty and Unicode tags; and moving the complete instrument directory.
Audio regression fixtures should follow Recs' existing 48 kHz, at-least-one-
second WAV convention; tiny direction examples above specify index order, not
replacement audio fixtures.

## Python Models

`recs.recsam.instrument.SampleInstrument` represents the root document, with
`Instrument` for shared settings and `SampleSlot` for each slot. The other
models are grouped into `playback`, `selection`, `processing`, `modulation`,
`controls`, and `events`; serialized enum values are defined in `enums`.
Import classes from their
defining modules, not from the package initializer.

Pass a parsed TOML mapping to `SampleInstrument.model_validate()`. These frozen
Pydantic models validate fields, local and instrument-wide references, inherited
playback constraints, and conservative combined spatial ranges without opening
audio files. Their list/dict members are ordinary mutable containers; treat a
validated definition as read-only or revalidate after modifying its contents.

`events.Trigger`, `events.Release`, and `events.ControlChange` represent the
performance events. `events.PerformanceEvent` is their discriminated union on
`kind`. After parsing an event, `SampleInstrument.validate_event()` validates
its control names and values against this instrument. Event models validate
shape, numeric domains, and scope targets; a future player validates ownership,
scheduling, and target pitch for selected tracked slots.

Slot settings are declarations, not resolved playback values. Use
`model_dump(mode="json", exclude_unset=True)` when serializing them, preserving
the distinction between an omitted setting and an explicit override equal to
its default. `model_fields_set` identifies supplied fields in each nested model.

A future loader must still check symlink containment, file existence and decoded
lengths, supported channel layouts, output-rate limits, and effective DSP
parameters. The models do not implement source evaluation, a sampler, a CLI,
or changes to the session-record schema.

## Additional Work Beyond The Prompt

None.
