# Sample Bank Format

## Status And Scope

This is a proposed format, not an implemented Recs feature or an existing
industry standard. It describes one playable sample bank: the sample files,
which notes and velocities select them, and how each selected sample plays.

A UTF-8 TOML file named `sample-bank.toml` holds the definition. Audio stays in
separate referenced files. One bank can contain any number of sample slots,
including several slots referencing different parts of the same file.

Version 1 defines audio sampling. It does not assume that reversing MIDI
messages or applying EQ to OSC packets has the same meaning as processing
audio. Recs' session record remains the common container for all time-based
media; this document defines the audio sample-bank behavior within that larger
system. Future media-specific playback semantics require a format revision,
not silently reinterpreting these audio fields.

The format is declarative. It cannot import Python, run shell commands, load
plugins, or depend on an installed sampler's opaque preset state. Clear names,
explicit units, and defined composition rules take precedence over matching
SFZ opcode names or syntax.

## Concepts

| Term | Meaning |
| --- | --- |
| Bank | One instrument or patch containing slots and bank-wide settings |
| Slot | A sample reference, note/velocity mapping, and local playback settings |
| Voice | One active playback instance of a slot, created by a trigger |
| Frame | One simultaneous sample value per channel in an audio file |
| Mapping | Conditions under which a trigger selects a slot |
| Modulation | A numeric adjustment driven by trigger values or live controllers/pressure |
| Tag | An arbitrary text label with no playback effect |

Overlapping mappings layer unless their slots explicitly belong to an alternate
selection set. TOML order does not establish priority, and the last matching
slot does not win. A repeated note-on creates new voices; it does not implicitly
replace existing ones.

## Complete Example

This bank has a quiet and a loud velocity layer. Its bank volume decreases
toward the top of the keyboard. One slot additionally reduces its own high-note
volume and raises the frequency of its local EQ band. The other uses `mirror`.

```toml
format_version = 1

[bank]
name = "Glass keys"
description = "Two velocity layers from a recorded glass instrument"
tags = ["glass", "pitched", "studio session"]

[bank.playback]
direction = "forward"
mode = "while_held"

[bank.envelope]
attack_seconds = 0.005
decay_seconds = 0.0
sustain_level = 1.0
release_seconds = 0.1

[bank.processing]
volume_db = -3.0
tuning_cents = 0.0

[[bank.processing.equalizer]]
id = "body"
frequency_hz = 700.0
gain_db = 1.5
quality_factor = 0.8

[[bank.modulation]]
target = "volume_db"
input = "note"
operation = "add"
interpolation = "linear"
points = [
  { input = 0, amount = 0.0 },
  { input = 60, amount = -1.0 },
  { input = 127, amount = -6.0 },
]

[[bank.modulation]]
target = "equalizer.body.gain_db"
input = "note"
operation = "add"
interpolation = "linear"
points = [
  { input = 0, amount = 0.0 },
  { input = 127, amount = -3.0 },
]

[[slots]]
id = "glass-soft"
name = "Soft strike"
sample = "audio/glass-soft.wav"
tags = ["soft", "clean attack"]

[slots.mapping]
lowest_note = 48
highest_note = 84
root_note = 60
minimum_velocity = 1
maximum_velocity = 79
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
quality_factor = 2.0

[[slots.modulation]]
target = "volume_db"
input = "note"
operation = "add"
interpolation = "linear"
points = [
  { input = 48, amount = 0.0 },
  { input = 84, amount = -2.0 },
]

[[slots.modulation]]
target = "equalizer.ring.frequency_hz"
input = "note"
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
lowest_note = 48
highest_note = 84
root_note = 60
minimum_velocity = 80
maximum_velocity = 127
pitch_tracking = true

[slots.playback]
direction = "mirror"

[slots.processing]
volume_db = -5.0
```

## Structure And Defaults

The root contains exactly `format_version`, `bank`, and `slots`. Version 1
requires `format_version = 1`, a nonempty `bank.name`, and at least one slot.
Every slot requires a unique `id`, `sample`, and a `mapping` table containing
`lowest_note`, `highest_note`, and `root_note`.

IDs use ASCII letters, digits, hyphens, and underscores. Names, descriptions,
and tags are Unicode text. An omitted slot `name` displays its ID. Descriptions
are optional on the bank and on individual slots.

| Setting | Default |
| --- | --- |
| `tags` | `[]` at either scope |
| `mapping.minimum_velocity` / `maximum_velocity` | `1` / `127` |
| `mapping.pitch_tracking` | `true` |
| Bank `playback.direction` | `"forward"` |
| Bank `playback.mode` | `"while_held"` |
| Slot `playback.start_frame` | `0` |
| Slot `playback.end_frame` | Decoded file's frame count, exclusive |
| Slot `playback.loop` | Absent: no repetition |
| Bank `selections` / slot `selection` | `[]` / absent: ordinary layering |
| Slot `choke_group` / `chokes` | Absent / `[]`: no choking |
| Slot `crossfades` | `[]`: unity layer weight |
| Slot `trigger` | `"note_on"` |
| Bank `sustain.enabled` / `controller` / `threshold` | `true` / `64` / `64` |
| Bank `articulations` / slot `articulations` | Absent / `[]`: no restriction |
| Bank `controller_defaults` | `{}`: unspecified controllers start at zero |
| `processing.volume_db` / `tuning_cents` | `0.0` independently at each scope |
| `processing.equalizer` | `[]` independently at each scope |
| `modulation` | `[]` independently at each scope |
| Bank `envelope.attack_seconds` / `decay_seconds` | `0.0` / `0.0` |
| Bank `envelope.sustain_level` / `release_seconds` | `1.0` / `0.0` |

Only playback direction, playback mode, and envelope fields inherit from the
bank. An absent slot override uses the effective bank value. The bank cannot
set trim boundaries because those refer to particular files.

Processing and modulation are separate stages, not inherited defaults: missing
slot processing means an identity slot stage, followed by the bank stage. It
does not mean copying the bank stage and applying it twice.

## Sample References And Time

`sample` names one audio file, relative to `sample-bank.toml`. References must
remain inside the bank directory after path resolution, including symlink
resolution. Absolute paths, URLs, and paths escaping with `..` are invalid.
The bank directory can be copied without changing its internal references.

The decoder provides channel count, native sample rate, and decoded frame
count. These are not duplicated as authoritative TOML fields. A player must
report an unsupported codec or channel layout, not silently drop a slot.

`start_frame` and `end_frame` select a half-open interval in the file's native
sample rate: `[start_frame, end_frame)`. They are non-negative integers, with
`start_frame < end_frame <= decoded_frame_count`. All channels share the same
boundaries and keep their file order. Compressed-file byte offsets have no
meaning here: these are decoded audio-frame positions.

Files with different native sample rates can share a bank. Sampler playback
converts them to the output rate; that conversion does not alter the stored
trim positions. Timing never depends on filenames or filesystem timestamps.

## Note And Velocity Mapping

Notes are integer MIDI note numbers from `0` through `127`; no ambiguous octave
names are stored. `lowest_note` and `highest_note` are inclusive and must be in
order. `root_note` is the note at which the sample has its original pitch before
tuning. It may lie outside the trigger range.

Velocity bounds are inclusive integers from `1` through `127`, also in order.
A note-on with velocity zero is a note-off, not a note-on sample trigger. A slot
matches only when its trigger kind and both mapping ranges match the event's
note and velocity context, as defined under Release And Pedal Samples.

With `pitch_tracking = true`, playback speed is multiplied by
`2 ** ((note - root_note) / 12)`. With it set to `false`, the mapped note does
not change playback speed. This is useful for percussion mapped across several
keys. Bank and slot tuning still apply in either case.

There is no hidden velocity-to-volume curve. Velocity chooses layers and can
modulate volume explicitly. A bank that needs quiet low-velocity notes adds a
`volume_db` modulation with `input = "velocity"`.

Voices triggered by one note-on share an output-time origin. Selected overlapping
slots are summed without automatic normalization. Version 1 specifies no
implicit voice stealing; alternate selection is explicit as described below.

## Alternate Sample Selection

Declare named selection sets on the bank and associate each alternative slot
with one set. A selection set is not a shared processing group:

```toml
[[bank.selections]]
id = "snare-takes"
mode = "cycle"

[[slots]]
id = "snare-a"
sample = "audio/snare-a.wav"
selection = "snare-takes"
[slots.mapping]
lowest_note = 38
highest_note = 38
root_note = 38

[[slots]]
id = "snare-b"
sample = "audio/snare-b.wav"
selection = "snare-takes"
[slots.mapping]
lowest_note = 38
highest_note = 38
root_note = 38
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

State is independent per set, MIDI channel, trigger kind, trigger note, and
ordered tuple of eligible slot IDs. Velocity layers therefore have independent
sequences when their eligible IDs differ; changing velocity without changing
that tuple advances the same sequence. State advances once per selected set
per triggering event, not per audio block or active voice. Returning to a
previous eligible tuple resumes its state. Loading or explicitly resetting a
bank clears all sequence state; ordinary note-offs do not reset it.

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
lowest_note = 46
highest_note = 46
root_note = 46
[slots.playback]
mode = "one_shot"

[[slots]]
id = "closed-hat"
sample = "audio/closed-hat.wav"
choke_group = "hats"
[slots.mapping]
lowest_note = 42
highest_note = 42
root_note = 42
[slots.playback]
mode = "one_shot"
[[slots.chokes]]
group = "hats"
mode = "fade"
fade_seconds = 0.005
```

Choke groups are bank-local IDs declared by membership, not processing groups
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
voices on that event's MIDI channel. Apply selected slots' choke rules to that
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
Choking is not a synthetic MIDI note-off and must not trigger release samples.

Conformance cases cover self-choking, layered event atomicity, channel isolation,
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
start = 60
end = 90
curve = "equal_power"
```

```toml
# Loud slot: complementary fade-in over the same interval.
[[slots.crossfades]]
input = "velocity"
direction = "in"
start = 60
end = 90
curve = "equal_power"
```

Each entry requires `input` (note/velocity or a live input defined below),
`direction` (`"in"` or `"out"`), and integer `start < end` in that input's valid
range. `curve` is `"linear"` (default) or `"equal_power"`. A slot may have one entry per
`(input, scope, controller, direction)`, allowing a fade-in and fade-out on each
axis. Static note/velocity inputs have no scope or controller field.

Clamp `t = (input_value - start) / (end - start)` to `[0, 1]`. Linear weights
are `t` for fade-in and `1 - t` for fade-out. Equal-power weights are
`sin(pi * t / 2)` and `cos(pi * t / 2)` respectively, with exact zero and one
at the endpoints. The opposing slots must use the same interval and curve to
be complementary. Their mapping ranges must both include the entire fade
interval for note/velocity inputs; a reader rejects a slot whose mapping cuts
off its nonzero transition. Live inputs do not widen or constrain key/velocity
mappings.

This example needs overlapping velocity mappings, unlike the disjoint layers
in the complete bank example. Crossfades neither widen mapping ranges nor
cause nonmatching slots to play. Matched slots with zero weight still create
voices and take part in selection and choking; silence is not a trigger filter.

Multiply all weights within a slot, then apply the result as a separate layer
gain alongside its envelope and volume before its EQ. Exact zero is silence,
not a fabricated finite dB value. Existing bank and slot volume curves still
apply; neither replaces the crossfade. Note/velocity weights are captured at
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

Declare articulation IDs, an initial selection, and explicit switch bindings.
Slots list the articulations in which they are eligible:

```toml
[bank.articulations]
ids = ["sustain", "plucked"]
default = "sustain"

[[bank.articulations.keys]]
note = 24
articulation = "sustain"
behavior = "latched"
consume = true

[[bank.articulations.keys]]
note = 25
articulation = "plucked"
behavior = "momentary"
consume = true

[[bank.articulations.controllers]]
controller = 1
minimum_value = 64
maximum_value = 127
articulation = "plucked"

[[slots]]
id = "pluck-middle"
sample = "audio/pluck.wav"
articulations = ["plucked"]
[slots.mapping]
lowest_note = 48
highest_note = 84
root_note = 60
```

When present, the bank table requires a nonempty, duplicate-free `ids` list
and a `default` naming one of them. IDs follow the usual ID syntax. Key and
controller binding lists default to empty. Slot articulation lists are
duplicate-free, must reference declared IDs, and default to `[]`, meaning
eligible in any articulation, not eligible in none. Tags remain descriptive.

Selection is independent per MIDI channel. A key binding requires a unique
note in `[0, 127]` and an articulation. `behavior` is `"latched"` (default) or
`"momentary"`; `consume` defaults to true. Latched note-on updates the persistent
selection. Momentary note-on temporarily overrides it until the matching key-up.
With several momentary switches held, the most recently pressed still-held
switch wins. Latched updates continue underneath that override; releasing the
last momentary switch exposes the latest persistent selection.

Repeated switch-note presses have FIFO key-up ownership, as ordinary notes do.
Switches are physical controls: sustain does not defer their key-ups. Consumed
key events update articulation state but create no musical note instances or
sample triggers. With `consume = false`, process the switch first, then process
the same event as an ordinary musical event. Its eventual musical release uses
its captured note-instance context.

A controller binding requires its controller number and inclusive integer
`minimum_value <= maximum_value`, all in `[0, 127]`, plus an articulation.
Ranges on the same controller must not overlap. A matching event updates the
persistent selection; an unmatched value leaves it unchanged. Controller
bindings are latched only and do not consume controller messages. A controller
may also affect sustain or modulation; articulation updates occur first.

Articulation filtering precedes alternate selection. A change affects future
note-on and pedal triggers only, never cancels or remaps an existing voice.
Each musical note instance captures its articulation at note-on; both physical
key-release samples and deferred note-release samples use that captured value,
even if the player switches while holding the note. Pedal samples use the
current articulation at the pedal transition.

Switching does not reset alternate-selection counters. An eligible set that
becomes active again resumes its previous state. Bank load/reset clears held
switches and restores the declared default on every channel without generating
musical events. Controller initialization alone does not fire switch bindings.

Conformance cases cover default selection, consumed/playable switch notes,
nested momentary switches, latched changes under a momentary switch, channel
isolation, controller gaps, and original-articulation release tails.

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

The bank supplies the default direction. A slot's explicit direction replaces
that default, so a backward bank plus a backward slot still plays backward,
not forward. Direction is not a numeric modulation target.

## Sustain Loops

A slot may add a loop inside its trimmed interval. Loop boundaries never inherit
from the bank because they address one particular file. This fragment belongs
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

## Release And Pedal Samples

Each slot's `trigger` is one of `"note_on"` (default), `"key_release"`,
`"note_release"`, `"pedal_press"`, or `"pedal_release"`. Key release means
physical key-up; note release means the logical release after sustain-pedal
deferral. A bank may use both deliberately; neither is an alias for the other.

```toml
[bank.sustain]
enabled = true
controller = 64
threshold = 64

[[slots]]
id = "key-tail"
sample = "audio/key-tail.wav"
trigger = "note_release"
[slots.mapping]
lowest_note = 48
highest_note = 84
root_note = 60
[slots.playback]
mode = "one_shot"

[[slots]]
id = "pedal-up"
sample = "audio/pedal-up.wav"
trigger = "pedal_release"
[slots.mapping]
lowest_note = 60
highest_note = 60
root_note = 60
pitch_tracking = false
[slots.playback]
mode = "one_shot"
```

`bank.sustain` defaults to the values shown. `controller` is an integer in
`[0, 127]`; `threshold` is in `[1, 127]`. Sustain is independent on each MIDI
channel, initially using the configured controller default (zero if omitted).
Values at or above the threshold mean pressed. Only transitions trigger pedal
samples; repeated values on the same side do not. If `enabled = false`, note-offs are immediate
and pedal-trigger slots are invalid rather than silently inert.

Every ordinary note-on creates a note instance owning its newly created voices
and original note/velocity context. MIDI 1 note-offs match the oldest still-
key-down instance on that channel and note. Keep this ownership even if its
audio exhausts before key-up, so its eventual note-off cannot release a newer
instance. Unmatched note-offs do nothing.

At matched key-up, generate `key_release` once if at least one owned note-on
voice is still active and has not already been released or choked. If sustain
is off, generate `note_release` under the same condition, then enter release
for owned while-held voices. If sustain is on, defer that logical release
until pedal-up. Recheck voice eligibility then: an instance whose original
voices all exhausted or were choked produces no release sample. New pedal
presses never resurrect or defer a release that already began.

Key/note-release slots use the original note-on note and velocity, not release
velocity. They are selected once per note instance, not once per original
layer, and cannot recursively generate further release samples. Chokes and
voice retirement are not key-up events. Release and pedal slots must explicitly
resolve to `one_shot` and cannot loop.

Pedal slots use their own `root_note` as a synthetic mapping/modulation note,
and `max(1, controller_value)` as velocity. Thus pedal-up value zero remains a
valid trigger context without being interpreted as another note-off. Their
mapping must contain their root note. These slots retain independent velocity
ranges, but create no held-note instance and require no physical key-down.
Pedal alternatives within one selection set and trigger kind must share a root
note, so selection and live-modulation initialization use one trigger context.

On pedal-up, update sustain state, release pending instances in note-on order,
and generate pedal-release samples. Derive all slot selections before applying
chokes: all voices generated by one incoming MIDI event belong to one atomic
batch and cannot choke one another. Note-release triggers retain their original
note context and use the selection-state keys defined above. Subsequent MIDI
events at the same frame retain their input order. Loading/resetting a bank
clears held notes and restores initial pedal state without generating release
or pedal samples.

Conformance cases include held-pedal key-up, pedal-up with several held notes,
one-shot exhaustion before release, repeated notes with FIFO ownership,
unmatched note-offs, threshold repeats, and absence of recursive tails.

## Note-Off And Envelope

Playback `mode` is `"while_held"` or `"one_shot"`:

- `while_held`: logical note release starts the matching voices' release stage;
  enabled sustain can defer it after physical key-up.
- `one_shot`: note-off does not shorten playback; the traversal runs to its end.

In either mode, a voice ends when its traversal is exhausted. Only an explicit
sustain loop repeats material; exhaustion manufactures no additional tail.
In one-shot mode, ordinary note-offs do not apply `release_seconds`; an explicit
release choke may do so. Note-instance ownership follows the release rules
above.

The envelope starts at zero, rises linearly to one during `attack_seconds`,
falls linearly to `sustain_level` during `decay_seconds`, and holds there.
When release starts, it proceeds from the current level and reaches zero linearly
over `release_seconds`. Zero-duration stages take effect immediately. Times are
finite non-negative seconds measured in output time, independent of pitch and
direction. `sustain_level` is in `[0, 1]`.

Bank envelope fields supply defaults. Slot fields override individual defaults
before voice creation. There is one effective envelope per voice, not two
multiplied envelopes. Envelope duration may outlast the available traversal;
the voice still ends at exhaustion.

## Bank And Slot Processing

Both scopes have the same `processing` table and `modulation` array. Bank
settings apply to every triggered voice, including voices whose slots contain
their own processing. Slots cannot bypass the bank processing stage.

`volume_db` is amplitude gain in decibels. Zero is unity; negative values
attenuate. The multiplier is `10 ** (volume_db / 20)`. Bank and slot volume add
in dB, so bank `-3.0` and slot `-2.0` produce `-5.0` before any modulation.

`tuning_cents` is an additional pitch adjustment. One hundred cents is one
semitone. Effective bank and slot tuning add, and the total playback multiplier
is:

```text
note_semitones = note - root_note if pitch_tracking else 0
pitch_ratio = 2 ** ((100 * note_semitones + bank_cents + slot_cents) / 1200)
```

Higher pitch shortens a traversal; this is sampling by playback-rate change,
not time stretching. Sample-rate conversion additionally uses the native rate
relative to the host's output rate.

### Equalizer

Each `[[bank.processing.equalizer]]` or `[[slots.processing.equalizer]]` entry
defines one bell-shaped parametric EQ band:

| Field | Meaning |
| --- | --- |
| `id` | Required unique band ID within that processing scope |
| `frequency_hz` | Required center frequency, greater than zero |
| `gain_db` | Required center-frequency boost or cut; zero is neutral |
| `quality_factor` | Required positive Q; larger values give narrower bands |

Version 1 specifies a digital peaking biquad using the coefficient convention
in the [W3C Audio EQ Cookbook](https://www.w3.org/TR/audio-eq-cookbook/).
For effective frequency `f`, gain `g`, quality factor `Q`, and host output
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

Bands run in listed order. Slot bands run before bank bands; lists concatenate
in the signal path rather than replacing each other. A band ID is local to its
scope: a slot band named `body` does not override a bank band named `body`.

### Signal Order

For each incoming MIDI event:

1. Update controller/pressure, articulation, pedal, and note-instance state and
   derive trigger contexts. Filter slots by trigger kind, articulation, and mapping, then
   select alternatives while retaining ordinary layers. Apply their choke rules
   to existing voices before creating the selected voices.
2. Resolve playback and envelope defaults, capture static curves, and initialize
   live modulation/crossfade state from current controller and pressure values.
3. Traverse the trimmed frames and optional loop in the effective direction,
   then resample for pitch.
4. Apply the effective amplitude envelope, crossfade weight, and slot volume,
   then slot EQ bands.
5. Apply bank volume, then bank EQ bands, independently to each voice.
6. Sum voices in the host's output channel layout without implicit downmixing.

Bank processing is conceptually per voice, not a single post-mix effect. This
is necessary because two simultaneously held notes may require different bank
EQ settings. A player may optimize equivalent calculations without changing
the result.

Processing uses floating-point headroom without implicit clipping or
normalization between stages. Final device limiting or file-encoding clipping
is a host/output policy, not a hidden bank operation. Interpolation and numeric
precision may differ between players; version 1 does not promise bit-identical
audio from every implementation.

## Scaling Across Notes And Velocities

`[[bank.modulation]]` affects the entire bank. `[[slots.modulation]]` affects
only its containing slot. Both use the same fields:

| Field | Meaning |
| --- | --- |
| `target` | Numeric processing parameter in the same scope |
| `input` | `"note"`, `"velocity"`, `"controller"`, `"channel_pressure"`, or `"note_pressure"` |
| `scope` | Live input scope; see Live Modulation; absent on note/velocity curves |
| `controller` | Required MIDI controller number for controller input only |
| `smoothing_seconds` | Live-input transition time, default `0.005`; absent on static curves |
| `operation` | `"add"` or `"multiply"` |
| `interpolation` | `"linear"` or `"step"`; default `"linear"` |
| `points` | Nonempty list of `{ input = integer, amount = number }` points |

Supported targets are `volume_db`, `tuning_cents`, and
`equalizer.BAND_ID.frequency_hz`, `equalizer.BAND_ID.gain_db`, or
`equalizer.BAND_ID.quality_factor`. Band IDs must name an existing band in the
same scope. A slot curve cannot reach into the bank to disable its processing.

Modulation for `volume_db`, `tuning_cents`, and EQ `gain_db` uses `add`; its
amount is in the target's units. Frequency and Q use `multiply`; amounts are
positive dimensionless ratios. Other target/operation combinations are invalid.
This prevents, for example, accidentally multiplying a negative dB value when
the intention was to double the amplitude.

Points have strictly increasing inputs: velocity inputs are in `[1, 127]`;
note, controller, and pressure inputs are in `[0, 127]`.
A single point defines a constant adjustment.
Linear interpolation operates on the numeric amounts between adjacent points.
Step interpolation holds the left point until the next point's input. At an
exact point, use that point's amount. Outside the listed range, hold the nearest
endpoint; do not extrapolate.

Coordinates are absolute MIDI values, not a percentage of occupied keys or of
the slot's mapped range. Adding or removing a slot cannot change a bank curve's
meaning. Curves apply equally to mono, stereo, and supported multichannel
samples.

At most one curve may exist per `(target, input, scope, controller)` in each
processing stage. Static inputs have no scope/controller. If several inputs
affect one target, add their amounts to its base value, or multiply their
ratios by its base value, according to the target's permitted operation.
Array order has no effect on that combination. Bank and slot scopes are then
combined using the processing rules above.

Note and velocity curves are evaluated from the trigger context and held for
the voice's lifetime. Controller and pressure curves can change throughout
playback as described below. Envelope timing remains separate; additional
envelopes and LFOs are still candidates rather than part of this specification.

For example, at note 60 the example's bank volume is `-3 + -1 = -4 dB`.
The soft slot's note curve is `-2/3 dB` there, so its slot volume is
`-2 - 2/3 dB`. Its combined volume is `-6 2/3 dB`, before envelope and EQ.
The bank's EQ gain curve and that slot's EQ frequency curve are both applied;
neither replaces the other.

## Live Modulation

Live curves use the same typed targets, point interpolation, and additive or
multiplicative composition as static curves. Bank curves still process each
voice independently; placing a curve on the bank does not imply that incoming
events on one channel affect every other channel.

```toml
[bank.controller_defaults]
"11" = 127

[[bank.modulation]]
target = "volume_db"
input = "controller"
controller = 11
scope = "channel"
operation = "add"
smoothing_seconds = 0.01
points = [
  { input = 0, amount = -60.0 },
  { input = 127, amount = 0.0 },
]
```

This initial volume is unchanged until controller 11 moves. `controller_defaults`
is a table of canonical decimal keys `"0"` through `"127"` and integer values
in `[0, 127]`. Unlisted values start at zero. Defaults initialize each channel
and the bank-wide controller state without generating switch or pedal-sample
events. Sustain's initial pressed state follows its configured default and
threshold. Pressure starts at zero.

Input scopes are:

| Input | Allowed scopes | Affected voices |
| --- | --- | --- |
| `controller` | `channel` (default), `bank` | Same-channel voices, or all bank voices |
| `channel_pressure` | `channel` (default), `bank` | Same-channel voices, or all bank voices |
| `note_pressure` | `note` (default and only value) | Active voices owned by matching channel/note instances |

`controller` is required only for controller input and is an integer in
`[0, 127]`. It is forbidden on other input types. Scope and smoothing fields
are forbidden on static note/velocity curves. A bank-scoped controller or
channel-pressure input uses the most recent matching event from any channel,
in event-stream order. Channel-scoped inputs use the voice's originating MIDI
channel.

MIDI 1 polyphonic key pressure applies to all active musical note instances of
that channel and note, including their associated release voices. New note
instances start with zero note pressure until a subsequent matching event;
they do not inherit stale pressure from a previous strike. Associated release
voices inherit their instance's latest value. Pedal voices have no note owner,
so note pressure is zero for them. This is not an MPE or microtonal specification.

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

Crossfades accept the same live inputs, scopes, controller numbers, and smoothing
times. Two overlapping slots can use these complementary fragments:

```toml
[[slots.crossfades]]
input = "controller"
controller = 1
scope = "channel"
direction = "out"
start = 0
end = 127
curve = "equal_power"
smoothing_seconds = 0.01
```

The other slot uses the same values with `direction = "in"`. For crossfades,
smooth the normalized position `t`, then compute the gain law. Matching times
and intervals therefore keep complementary pairs complementary throughout a
transition. Do not smooth their sine/cosine gains independently. Initialize new
voices at the current unsmoothed target position, as with ordinary live curves;
only equally initialized paired voices have that complementarity guarantee.

Controller updates change existing voices' gains but do not create or reselect
slots. Both layers must be selected at trigger time, including a layer whose
initial weight is zero. A layer that has exhausted its sample cannot be
resurrected by moving a controller. Articulation switches remain future-trigger
selectors, not live crossfades.

### Reset And Validation

Explicit bank reset stops voices, clears note/selection/switch state and ramps,
restores controller defaults and zero pressure, and restores default
articulations. It generates no release samples. New voices thereafter use that
initial state. Do not equate arbitrary incoming controller messages with a bank
reset unless their behavior is explicitly specified.

Validate effective parameters across all applicable static and live inputs,
including simultaneous contributions and smoothing trajectories. Positive
frequency/Q multipliers must remain positive; effective EQ frequencies must
remain below Nyquist. A player must reject unsafe combinations at load time,
not silently clamp modulation during playback. Conservative interval analysis
is acceptable if it reports the rejected parameter and range clearly.

Conformance cases cover configured initial values, channel/bank/note scopes,
pressure on repeated notes, overlapping ramps, mid-block updates, state-preserving
EQ changes, paired live fades, exhausted layers, and reset without spurious
triggers. Replaying identical events with different block sizes must produce
the same parameter trajectories.

## Tags

`bank.tags` and each slot's `tags` are independent lists of zero or more
nonempty text strings. Spaces and Unicode are allowed. Tags are case-sensitive;
readers must not split a tag on spaces, normalize its spelling, or interpret
punctuation as hierarchy. An omitted list is the same as `[]`.

Duplicates within one list are invalid. A bank and a slot may share the same
tag. Written order is preserved for display but has no semantic meaning.

Bank tags describe the instrument as a whole; slot tags describe individual
samples or mappings. Bank tags are not copied into slot lists. A UI may offer
combined searching, but must retain their distinct scopes. Tags never select
notes, change volume, or secretly enable articulations.

## Relationship To Recs Sessions And Edits

A standalone bank needs only `sample-bank.toml` and its referenced audio files.
A bank generated by a Recs edit lives in the edit's new output session:

```text
glass-bank/
  session-record.jsonl
  edit.toml
  sample-bank.toml
  audio/
    glass-soft.wav
    glass-hard.wav
```

These are three different metadata artifacts, not three copies of one schema:

- `session-record.jsonl` indexes generated media and records lifecycle and
  provenance, following [Session Record Format](session-record-format.md).
- `edit.toml` preserves the resolved transformation that produced the result,
  as specified in the existing editing plan.
- `sample-bank.toml` describes how the result responds to future performance
  events. It does not duplicate edit history or source-session selectors.

The bank references the generated audio files directly, not an input session's
files. Its playback requires neither input sessions nor the edit recipe. A
player does not execute `edit.toml` when loading a bank.

The output session records the generated audio normally. The bank definition's
relative path may be identified in lifecycle metadata; it is not disguised as
an audio file or embedded as sample quantity data. Producing a bank from a
mixed-media session does not implicitly copy MIDI, OSC, or other unsupported
media into the output.

## Validation And Portability

A reader validates the complete bank before accepting it for playback:

- Recognized format version, field names, and enum values; no unknown values
  silently ignored and no evaluation of embedded code.
- Required fields, unique slot IDs, local EQ IDs, and nonempty names/tags.
- Unique selection-set IDs, valid selection modes, and existing set references.
- Existing choke-group targets, unique per-slot targets, and valid choke modes
  and fade times.
- Crossfade input ranges, unique input/scope/controller/direction keys, gain
  curves, and mappings covering each static crossfade transition.
- Trigger kinds, sustain settings, one-shot release/pedal playback, and pedal
  mappings containing their synthetic root note.
- Declared articulation references and default, unique keyswitch notes, and
  nonoverlapping controller-selector ranges.
- Note/velocity bounds, trim intervals, existing contained audio files, and
  supported decoding and output channel layouts.
- Contained loop intervals, valid loop/playback-mode combinations, and permitted
  crossfade lengths and directions.
- Finite numeric values, positive frequencies and Q, non-negative envelope
  times, and valid sustain levels.
- Existing modulation targets, permitted operations, ordered point inputs,
  and positive multiplicative amounts.
- Valid live input scopes, controller defaults and numbers, and smoothing times.
- Valid effective parameters over every static/live input combination that can
  affect each slot, including bank and slot curves. Validation uses the host
  output rate for the EQ frequency limit and is repeated if that rate changes.

Errors identify the slot, band, or curve and the offending field. A player that
cannot support a declared feature must reject the bank with an explanation,
not silently skip the feature and claim to have loaded it faithfully.

Useful conformance cases include layered velocity mappings; independent bank
and slot volume curves; bank and slot EQ with identical local band IDs; all
three directions for one-, two-, and four-frame traversal definitions; note-off
in each mode; empty and Unicode tags; and moving the complete bank directory.
Audio regression fixtures should follow Recs' existing 48 kHz, at-least-one-
second WAV convention; tiny direction examples above specify index order, not
replacement audio fixtures.

No sampler implementation, command-line interface, format converter, loop
engine, or session-record schema change is included in this document-only task.

## Additional Work Beyond The Prompt

None.
