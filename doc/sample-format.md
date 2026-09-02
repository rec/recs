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
| Mapping | Conditions under which a MIDI note-on selects a slot |
| Modulation | A numeric parameter adjustment based on the triggering note or velocity |
| Tag | An arbitrary text label with no playback effect |

Overlapping mappings layer: every matching slot creates a voice. TOML order
does not establish priority, and the last matching slot does not win. A repeated
note-on creates new voices; it does not implicitly replace existing ones.

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
A note-on with velocity zero is a note-off, not a sample trigger. A slot matches
only when both the note and velocity are within its bounds.

With `pitch_tracking = true`, playback speed is multiplied by
`2 ** ((note - root_note) / 12)`. With it set to `false`, the mapped note does
not change playback speed. This is useful for percussion mapped across several
keys. Bank and slot tuning still apply in either case.

There is no hidden velocity-to-volume curve. Velocity chooses layers and can
modulate volume explicitly. A bank that needs quiet low-velocity notes adds a
`volume_db` modulation with `input = "velocity"`.

Voices triggered by one note-on share an output-time origin. Overlapping slots
are summed without automatic normalization. Version 1 specifies no implicit
voice-stealing or random selection policy.

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

Mirror does not mean indefinite ping-pong looping. Version 1 has no looping
fields. Every direction eventually exhausts its selected material.

The bank supplies the default direction. A slot's explicit direction replaces
that default, so a backward bank plus a backward slot still plays backward,
not forward. Direction is not a numeric modulation target.

## Note-Off And Envelope

Playback `mode` is `"while_held"` or `"one_shot"`:

- `while_held`: note-off starts the release stage of the matching voices.
- `one_shot`: note-off does not shorten playback; the traversal runs to its end.

In either mode, a voice ends when its traversal is exhausted. Exhaustion does
not introduce a loop or manufacture an additional audio tail. In one-shot mode
`release_seconds` has no effect. Repeated notes need distinct voice ownership;
this file format does not replace the host's MIDI note-event handling.

The envelope starts at zero, rises linearly to one during `attack_seconds`,
falls linearly to `sustain_level` during `decay_seconds`, and holds there. In
while-held mode, release starts at the current level and reaches zero linearly
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

For each note-on:

1. Select matching slots using their note and velocity ranges.
2. Resolve playback and envelope defaults, and evaluate bank and slot modulation.
3. Read the trimmed frames in the effective direction and resample for pitch.
4. Apply the effective amplitude envelope and slot volume, then slot EQ bands.
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
| `input` | `"note"` or `"velocity"` from the triggering note-on |
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

Points have strictly increasing inputs: note inputs are in `[0, 127]` and
velocity inputs in `[1, 127]`. A single point defines a constant adjustment.
Linear interpolation operates on the numeric amounts between adjacent points.
Step interpolation holds the left point until the next point's input. At an
exact point, use that point's amount. Outside the listed range, hold the nearest
endpoint; do not extrapolate.

Coordinates are absolute MIDI values, not a percentage of occupied keys or of
the slot's mapped range. Adding or removing a slot cannot change a bank curve's
meaning. Curves apply equally to mono, stereo, and supported multichannel
samples.

At most one curve may exist per `(target, input)` in a scope. If both note and
velocity affect one target, add their amounts to its base value, or multiply
their ratios by its base value, according to the target's permitted operation.
Array order has no effect on that combination. Bank and slot scopes are then
combined using the processing rules above.

Curves are evaluated at note-on and held for the voice's lifetime. They scale
parameters across a bank's trigger range, not across elapsed sample time.
Envelope timing is separate. Live controller changes and general time-based
automation are not part of version 1.

For example, at note 60 the example's bank volume is `-3 + -1 = -4 dB`.
The soft slot's note curve is `-2/3 dB` there, so its slot volume is
`-2 - 2/3 dB`. Its combined volume is `-6 2/3 dB`, before envelope and EQ.
The bank's EQ gain curve and that slot's EQ frequency curve are both applied;
neither replaces the other.

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
- Note/velocity bounds, trim intervals, existing contained audio files, and
  supported decoding and output channel layouts.
- Finite numeric values, positive frequencies and Q, non-negative envelope
  times, and valid sustain levels.
- Existing modulation targets, permitted operations, ordered point inputs,
  and positive multiplicative amounts.
- Valid effective parameters over every note/velocity combination that can
  trigger each slot, including bank and slot curves. Validation uses the host
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
