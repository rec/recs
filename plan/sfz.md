# Remaining Standard SFZ Import Work

## Current Baseline

`recs.recsam.sfz.read()` already returns `SfzCompileResult`, containing a validated
native uFor instrument when one can be constructed and an ordered collection of
unimplemented features with source locations. The completed correctness work
includes velocity response, asset-aware loop and channel defaults, envelope
shape mapping, release-trigger distinctions, half-open loop endpoints, and
basic inheritance. Pure parsing, compilation and export now live in
`ufor.sfz`; recs only resolves paths and supplies measured asset metadata.
Key-dependent amplitude, partial pitch-key tracking, pitch-by-velocity, and
velocity-dependent amplifier envelope durations are also imported.
Key and velocity crossfades preserve the separate mapping eligibility ranges;
deterministic SFZ random ranges have their own selection condition. The
documented `lovel` default of MIDI velocity 1 is preserved. Finite `loop_count`
values now map to native loop `repeat_count` and round-trip.
The `pitch` fine-tuning alias and integral `transpose` bounds are handled.
Standard `tune` and `volume` bounds are enforced on import and export, and
numeric SFZ group spellings share one choke identity. Conflicting `key` and
`pitch_keycenter` order is diagnosed where players disagree.
SFZ `off_by` is translated from its victim-side meaning into native trigger-side
chokes, including distinct `off_mode` values; export reverses that mapping.
SFZ `phase=invert` maps to generic polarity inversion independently of pan.
Positive SFZ `count` values map to native one-shot `play_count` without
retriggering envelopes; player-dependent `count=0` remains diagnosed.
SFZ `loop_type` now preserves a loop's direction independently of whole-sample
`direction`, including backward and alternating loops.
SFZ `delay` maps to a native delayed voice start distinct from envelope delay;
one-shot note-off behavior that varies by player remains diagnosed.
SFZ round-robin positions can be imported with the explicit `all_note_ons`
counter rule; the default reports them as unsupported because SFZ players
disagree on counter behavior.
Release-triggered sequence and random conditions that cannot use the native
note-on state are diagnosed rather than approximated. Overlapping regions
remain independent layers.
The pinned SFZ v1/v2 registry classifies 453 opcodes and the standard headers,
drives unsupported-feature diagnostics, and generates the
[support table](../../ufor/doc/sfz-support.md). SFZ 2 `#define` values expand
at use sites with recursive and undefined variables rejected. Unsupported
`<curve>`, `<effect>`, and `<sample>` sections have located diagnostics.

The remaining goal is a lossless, well-diagnosed import of useful,
non-vendor-specific SFZ 1 and SFZ 2 behavior. Unsupported behavior must remain
visible; it must never be silently approximated.

Vendor extensions remain outside the compatibility promise. A general recsam
concept should be added only when it is useful independently of SFZ.

## 2. New General Recsam Concepts

Design these independently before adding importer mappings:

- voice limits, voice stealing, repeated-trigger masking, and release-tail
  termination;
- end fade, stereo width, channel position, and channel swapping;
- mappings for the richer shared envelope/LFO behavior, including LFO fade-in;
- exact conversion between SFZ equalizer bandwidth and recsam resonance, if the
  transfer functions can be specified and tested.

Do not add SFZ opcode names to the native uFor model. Filters remain blocked on a separate
filter design.

## 3. Controller Bindings

The separate `performance_binding` score now describes MIDI channel-to-part,
note identity, and named-control CC conversion independently of host adapters.
SFZ import can return it alongside the instrument when the caller explicitly
supplies an instrument reference, part, and repeated-key release rule. Shared
`lochan`/`hichan` ranges map; mixed per-region ranges remain diagnosed.
Other protocols need their own explicit input profile.

Next consider CC conditions and modulation, pitch
bend, aftertouch, key switches, previous-key conditions, initial CC values, and
controller curves. Until that format exists, report these as requiring a
controller binding.

## Explicit Deferrals

- filters, filter envelopes, and filter LFOs;
- beat synchronization without a transport and tempo model;
- output buses, sends, and `<effect>` without a routing graph;
- generated waveforms and waveguides without a synthesis-source model;
- random delay, offset, pitch, and gain without reproducible random state;
- MD5 assertions unless recs adopts general asset verification;
- vendor extensions, including `#include`.

## Tests

Use compact handwritten SFZ fixtures and regression snapshots. Cover every
supported opcode's defaults, bounds, and units; inheritance order; mono and
stereo assets; embedded loops; diagnostics for all standard unsupported
opcodes; `#define`; crossfades; coherent alternatives; and exact source
locations after preprocessing.

Audio fixtures must remain WAV files at 48,000 samples per second and at least
one second long. Ambiguous reference behavior is a documented deferral, not a
fixture copied from one player's interpretation.

## Completion Criteria

- Every standard SFZ 1 and SFZ 2 construct has one registry classification.
- Every successful conversion preserves all represented behavior.
- Every unsupported construct has a precise location and explanation.
- The generated support table comes from the runtime registry.
- Recsam additions remain protocol-neutral and independently useful.
- The full suite does not access real MIDI devices.

## Additional work beyond the prompt

None.
