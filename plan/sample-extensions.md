# Sample extensions

## Scope

The first extension adds a portable **voice-management policy** to a sample
instrument. It makes polyphony and repeated triggering explicit in an
`InstrumentScore`, without adding a sampler, generating audio, or selecting a
runtime language.

The existing model already covers selections, chokes, articulations, envelopes,
LFOs, slices, channel maps, and per-slot playback. This extension gives a future
player one unambiguous rule for the voice pressure that those existing features
can create.

## Portable model

Add `voice_policy` to `SampleInstrument.instrument`. It is absent when an
instrument deliberately leaves voice count unconstrained. When present, it has:

- `maximum_voices`: a positive integer, counting each rendered slot voice, not
  source triggers. A layered trigger can therefore consume several voices.
- `same_key`: one of `stack`, `release`, or `replace`.
  - `stack` retains earlier matching voices.
  - `release` sends matching voices through their ordinary release path before
    creating the new ones.
  - `replace` ends matching voices immediately before creating the new ones.
- `overflow`: one of `release_oldest` or `replace_oldest`, applied until the
  instrument has room for every voice selected by the incoming trigger.

A matching voice has the same logical instrument input key and articulation as
the incoming trigger. It is not merely a slot with the same mapped pitch. This
keeps pitch-transposed instruments and keyswitches from creating accidental
matches.

`same_key` is resolved first. Then the player applies `overflow` to the oldest
remaining active voices, ordering ties by trigger ordinal. The policy does not
override an explicit choke: chokes are processed before general overflow.

## First implementation

Implement this as Ufor model data and validation only:

1. Add enums and a frozen `VoicePolicy` model under `ufor.samples`.
2. Add an optional `voice_policy` field to the instrument declaration.
3. Add JSON/TOML round-trip and validation cases, including positive limits and
   all declared policies.
4. Document the policy in Ufor's instrument-format reference.
5. Update Recs to depend on the resulting Ufor revision.

This defines the contract that a player must follow; it does not claim that
Recs currently has voices to manage.

## Deferred extensions

The following remain separate design and implementation work:

- slot groups and inherited selection or sound settings;
- linked microphone layers, output routing, and alignment offsets;
- seeded random variation and exact alternate-selection traversal;
- resonant filters and their modulation/stability rules;
- instrument preparation, a renderer, offline playback, live playback, or a
  VST host.

Those extensions build on this policy but should be specified one at a time.

## Additional work beyond the prompt

None.
