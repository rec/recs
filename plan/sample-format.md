# Sample Format Additions

## Scope

Additions to [Sample Bank Format](../doc/sample-format.md). Each section records
whether it has been incorporated into the specification. Unmarked suggestions
remain candidates for review; inclusion is not a commitment to implement them.

Specification work does not implement a sampler.
Microtonality is covered by a separate specification and is out of scope.

Keep the format declarative, use clear names and explicit units, and build on
the existing bank/slot processing and modulation rules. Reuse those mechanisms
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
- Specify the order of note/velocity filtering and alternate selection so an
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

- Define fade-in and fade-out ranges over notes or velocities.
- Reuse the existing volume-curve machinery and provide explicit complementary
  crossfade rules rather than a second unrelated gain system.
- Specify the gain law and behavior where more than two layers overlap.
- Keep crossfading distinct from alternate selection and automatic normalization.

Reference: [SFZ crossfades](https://sfzformat.com/tutorials/sustained_note_basics/).

### 5. Release And Pedal Samples

Status: specified in [Release And Pedal Samples](../doc/sample-format.md#release-and-pedal-samples).
Playback implementation remains pending.

Represent piano mechanics, guitar release noises, and separately recorded
instrument tails.

- Permit sample triggers on note release, pedal press, and pedal release.
- Define sustain-pedal behavior for existing voices and deferred note releases.
- State whether a release sample follows physical key release or the eventual
  end of pedal-held sustain.
- Define release-sample ownership so unmatched note-offs or already-ended voices
  do not produce unintended sounds.

Reference: [SFZ triggers](https://sfzformat.com/legacy/).

### 6. Named Articulations

Status: specified in [Named Articulations](../doc/sample-format.md#named-articulations).
Playback implementation remains pending.

Select explicit playing styles such as bowed/plucked, muted/open, or
sustained/staccato.

- Give articulations names and select them through keyswitches or controller
  values.
- Define initial selection, persistent versus momentary selection, and whether
  switching affects only future triggers or also existing voices.
- State whether a keyswitch is consumed or may also trigger a playable slot.
- Keep tags descriptive. A tag must not secretly become an articulation switch.

Reference: [SFZ keyswitches](https://sfzformat.com/tutorials/sustained_note_basics/).

## Expressive Controls

### 7. Live Modulation

Status: specified in [Live Modulation](../doc/sample-format.md#live-modulation).
Playback implementation remains pending.

Allow controllers and pressure to change parameters while a note is sounding.

- Extend the existing modulation model beyond values sampled only at note-on.
- Support expressive volume, filter, and layer-balance changes.
- Specify bank, channel, and individual-voice scope where applicable.
- Define smoothing, initial controller values, and reset behavior to prevent
  abrupt parameter jumps and ambiguous playback.

Reference: [SFZ modulation capabilities](https://sfzformat.com/).

### 8. Additional Envelopes And LFOs

Support evolving sounds through filter envelopes, tremolo, and other periodic
or time-dependent parameter changes.

- Reuse typed modulation targets for additional envelopes and oscillators.
- Define rates, depths, curve shapes, phase, and retrigger behavior explicitly.
- Distinguish per-voice modulators from bank-wide modulators.
- Specify how these contributions combine with note, velocity, and controller
  modulation without depending on declaration order.

Reference: [Decent Sampler modulators](https://www.decentsamples.com/2022/08/19/how-to-add-lfos-and-extra-envelopes-to-your-decent-sampler-instruments/).

### 9. Voice Limits And Retrigger Behavior

Make polyphony and repeated-note behavior predictable while controlling CPU
and memory use.

- Define bank-wide and, if groups are retained, per-group voice limits.
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
- Define precedence and signal order across bank, group, and slot settings.
- Distinguish inherited defaults from additional processing stages, as the
  current bank/slot model already does.
- Keep grouping, alternate selection, and choking conceptually distinct even
  when they refer to the same set of slots.

### 11. Synchronized Microphone Layers And Output Routing

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
- Reproduce results for the same bank, event stream, and declared initial state.
  This does not require bit-identical audio from different rendering engines.

## Suggested Order

Items 1 through 7 are now incorporated into the proposed format with TOML
examples, defaults, composition rules, and conformance cases. They are not
implemented in a playback engine.

Review the remaining candidates before expanding the specification further.
Review named groups before finalizing additional group-scoped behavior, and
resolve reproducible randomness before promising cross-player seeded renders.
General voice limits, additional envelopes/LFOs, and items 10 through 13 remain
unapproved candidates. Playback implementation follows the separate
[Sample Playback](sample-playback.md) plan.

## Deferred

Granular playback, time stretching, and arbitrary effect chains are not proposed
for the first expansion. Their implementation complexity and portability costs
are substantially greater than the features above.

## Additional Work Beyond The Prompt

None.
