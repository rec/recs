# Sample Format Additions

## Scope

Additions to [Recsam Instrument Format](../doc/sample-format.md). Each section
records whether it has been incorporated into the specification. Unmarked suggestions
remain candidates for review; inclusion is not a commitment to implement them.

Specification work does not implement a sampler.
Microtonality is covered by a separate specification and is out of scope.

The spec and recsam models now use protocol-neutral performance events,
unrestricted integer selection keys, separate target/reference frequencies,
and normalized named controls. MIDI/OSC bindings belong to future host adapters;
the retained features below must not introduce transport-specific state.

Keep the format declarative, use clear names and explicit units, and build on
the existing instrument/slot processing and modulation rules. Reuse those mechanisms
where possible instead of adding a separate syntax for every feature.

## Highest-Value Candidates

### 1. Sustain Loops

Status: specified in [Sustain Loops](../doc/sample-format.md#sustain-loops).
Playback implementation remains pending.

Allow sustained instruments to keep sounding without requiring arbitrarily
long recordings.

- Define explicit loop start and end frames within the selected sample range.
- Support an optional crossfade at the loop join to reduce discontinuities.
- Specify whether looping ends on note release or continues through the release
  envelope, and how playback leaves the loop for the remaining sample tail.
- Keep repetition separate from `direction`. Forward, backward, and mirror
  describe traversal; looping determines whether a traversal repeats.
- Define boundary behavior for every direction without duplicating turning
  frames accidentally.

Reference: [SFZ looping](https://sfzformat.com/opcodes/loopmode/).

### 2. Alternate Sample Selection

Status: specified in [Alternate Sample Selection](../doc/sample-format.md#alternate-sample-selection).
Playback implementation remains pending.

Allow several takes of the same sound to vary repeated notes naturally.

- Cycle through takes in order, choose randomly, or shuffle without immediate
  repetition.
- Distinguish selection from layering: selection chooses alternatives, whereas
  layering plays all matching slots.
- Define the scope of a sequence counter, such as one instrument or articulation,
  and which events advance it.
- Specify the order of key/velocity filtering and alternate selection so an
  unavailable alternative does not silently create a missing note.

Reference: [SFZ round robins](https://sfzformat.com/tutorials/drum_basics/).

### 3. Choke Groups

Status: specified in [Choke Groups](../doc/sample-format.md#choke-groups).
Playback implementation remains pending.

Let one sound terminate another, such as a closed hi-hat stopping an open
hi-hat or a new phrase replacing a previous phrase.

- Name the voices a trigger can stop and distinguish this from ordinary grouping.
- Specify immediate stop, a short fade, or entry into the existing release stage.
- Define whether repeated triggers stop earlier voices of the same slot.
- Apply choking to existing voices, without accidentally stopping voices created
  by the same trigger.

Reference: [SFZ exclusive groups](https://sfzformat.com/legacy/).

### 4. Layer Crossfades

Status: specified in [Layer Crossfades](../doc/sample-format.md#layer-crossfades).
Playback implementation remains pending.

Replace abrupt key-range and velocity-layer transitions with smooth blends.

- Define fade-in and fade-out ranges over keys or normalized velocities.
- Reuse the existing volume-curve machinery and provide explicit complementary
  crossfade rules rather than a second unrelated gain system.
- Specify the gain law and behavior where more than two layers overlap.
- Keep crossfading distinct from alternate selection and automatic normalization.

Reference: [SFZ crossfades](https://sfzformat.com/tutorials/sustained_note_basics/).

### 5. Release And Sustain Samples

Status: specified in [Release And Sustain Samples](../doc/sample-format.md#release-and-sustain-samples).
Playback implementation remains pending.

Represent piano mechanics, guitar release noises, and separately recorded
instrument tails.

- Permit samples on explicit release, logical release, and sustain transitions.
- Define a named sustain control for existing voices and deferred releases.
- State whether a release sample follows the explicit Release event or the
  eventual end of sustained playback.
- Define release-sample ownership by trigger ID so unmatched releases or ended voices
  do not produce unintended sounds.

Reference: [SFZ triggers](https://sfzformat.com/legacy/).

### 6. Named Articulations

Status: specified in [Named Articulations](../doc/sample-format.md#named-articulations).
Playback implementation remains pending.

Select explicit playing styles such as bowed/plucked, muted/open, or
sustained/staccato.

- Give articulations names and select them through keyswitches or named-control
  values.
- Define initial selection, persistent versus momentary selection, and whether
  switching affects only future triggers or also existing voices.
- State whether a keyswitch is consumed or may also trigger a playable slot.
- Keep tags descriptive. A tag must not secretly become an articulation switch.

Reference: [SFZ keyswitches](https://sfzformat.com/tutorials/sustained_note_basics/).

## Expressive Controls

### 7. Live Modulation

Status: specified in [Named Controls And Live Modulation](../doc/sample-format.md#named-controls-and-live-modulation).
Playback implementation remains pending.

Allow named controls, including pressure, to change parameters while a voice sounds.

- Extend the existing modulation model beyond values sampled only at trigger start.
- Support expressive volume, EQ, and layer-balance changes. New filter types
  require separate consideration.
- Specify independent instrument, logical-part, and trigger scopes.
- Define smoothing, declared control defaults, and reset behavior to prevent
  abrupt parameter jumps and ambiguous playback.

Reference: [SFZ modulation capabilities](https://sfzformat.com/).

### 8. Additional Envelopes And LFOs

Status: specified in [Release And Envelope](../doc/sample-format.md#release-and-envelope)
and [Modulation Envelopes And LFOs](../doc/sample-format.md#modulation-envelopes-and-lfos).
Playback implementation remains pending. Filter design is excluded.

Support evolving sounds through pitch envelopes, tremolo, and other periodic
or time-dependent parameter changes.

- Reuse typed modulation targets for additional envelopes and oscillators.
- Define rates, depths, curve shapes, phase, and retrigger behavior explicitly.
- Distinguish per-voice modulators from instrument-wide modulators.
- Specify how these contributions combine with key, velocity, and named-control
  modulation without depending on declaration order.

Reference: [Decent Sampler modulators](https://www.decentsamples.com/2022/08/19/how-to-add-lfos-and-extra-envelopes-to-your-decent-sampler-instruments/).

### 9. Voice Limits And Retrigger Behavior

Make polyphony and repeated-note behavior predictable while controlling CPU
and memory use.

- Define instrument-wide and, if groups are retained, per-group voice limits.
- Specify how repeated notes interact with existing voices.
- Make voice retirement explicit, including which voice is chosen and whether
  it fades or stops immediately.
- Define interactions with layered slots, choke groups, pedal-held voices, and
  release samples. State whether a limit counts triggers or individual voices.

Reference: [SFZ voice controls](https://sfzformat.com/opcodes/).

## Especially Useful For Recs

### 10. Named Slot Groups

Share settings across a drum, articulation, or microphone position without
repeating them in every slot.

- Start with one grouping level rather than arbitrary nested inheritance.
- Define precedence and signal order across instrument, group, and slot settings.
- Distinguish inherited defaults from additional processing stages, as the
  current instrument/slot model already does.
- Keep grouping, alternate selection, and choking conceptually distinct even
  when they refer to the same set of slots.

### 11. Synchronized Microphone Layers And Output Routing

Partial status: mono panning and stereo balance are specified in
[Panning And Stereo Balance](../doc/sample-format.md#panning-and-stereo-balance).
Microphone linking, channel selection, and named routing remain candidates;
no playback implementation is included.

Keep close, room, and ambient recordings aligned while allowing independent
levels and named outputs.

- Trigger linked microphone layers together and preserve their relative timing.
- Make alternate-take selection consistent across linked microphones.
- Define channel selection, mono panning, and stereo balance separately.
- Specify named output routing and explicit channel layouts; do not silently
  downmix or discard channels.
- Decide whether a declared alignment offset is required for recordings whose
  file starts differ, rather than guessing from filenames.

### 12. Named Slices

Map marked regions of a longer recording to notes without duplicating audio.

- Give slices stable names and native-frame boundaries.
- Let slots refer to those slices, preserving a single authoritative location
  for their boundaries rather than duplicating trim values.
- Reuse the existing trimmed-sample playback semantics.
- Keep slice naming and editing separate from the choice of which notes trigger
  each slice.

### 13. Reproducible Variation

Allow offline rendering to reproduce a performance that uses alternate takes
or randomized parameter values.

- Define deterministic seeds and sequence-reset rules.
- Specify the random-selection algorithm, not merely a seed whose meaning
  differs between players.
- Ensure processing block size and unrelated voices do not accidentally change
  a slot's selection sequence.
- Reproduce results for the same instrument, event stream, and declared initial state.
  This does not require bit-identical audio from different rendering engines.

## Suggested Order

Items 1 through 8, mono panning/stereo balance, and pitch bend are now
incorporated into the proposed format with TOML
examples, defaults, composition rules, and conformance cases. They are not
implemented in a playback engine.

Review the remaining candidates before expanding the specification further.
Review named groups before finalizing additional group-scoped behavior, and
resolve reproducible randomness before promising cross-player seeded renders.
General voice limits and the remaining parts of items 10 through 13 remain
unapproved candidates. Playback implementation follows the separate
[Sample Playback](sample-playback.md) plan.

## Additional Approved Controls

- Panning and stereo balance: separate mono placement and stereo-channel
  attenuation, explicit gain laws, combined instrument/slot offsets, typed modulation,
  and channel-layout validation are specified.
- Pitch bend: a declared bipolar control with instrument/slot routes to tuning,
  explicit range in cents, smoothing, and part or trigger scope is specified in
  [Pitch Bend And Pressure](../doc/sample-format.md#pitch-bend-and-pressure).
  There is no implicit pitch-wheel state or separate pitch-bend settings table.
  This does not add microtonality or MIDI RPN/NRPN handling.

Both remain specification work, not implemented playback features.

## Deferred

Resonant filters need separate consideration and are not added by the envelope,
LFO, panning, or pitch-bend changes. Existing peaking EQ is unchanged.

Granular playback, time stretching, and arbitrary effect chains are not proposed
for the first expansion. Their implementation complexity and portability costs
are substantially greater than the features above.

## Additional Work Beyond The Prompt

None.
