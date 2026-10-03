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
SFZ `sample_fadeout` maps to a native linear end fade for unlooped single
playback; `width=-100` swaps stereo channels when no pan is active, and
`ampeg_start` maps to the native envelope's initial level.
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
Numeric SFZ `polyphony` now maps to group-scoped native voice pools with
oldest-immediate retirement. The default retains the instrument with a located
assumption diagnostic; callers can accept the rule explicitly. Conflicting
limits, legato variants, and limits that may reject simultaneous layers remain
diagnosed.
The pinned SFZ v1/v2 registry classifies 453 opcodes and the standard headers,
drives unsupported-feature diagnostics, and generates the
[support table](../../ufor/doc/sfz-support.md). SFZ 2 `#define` values expand
at use sites with recursive and undefined variables rejected. Unsupported
`<curve>`, `<effect>`, and `<sample>` sections have located diagnostics.

The remaining goal is a lossless, well-diagnosed import of useful,
non-vendor-specific SFZ 1 and SFZ 2 behavior. Unsupported behavior must remain
visible; it must never be silently approximated.

Vendor extensions remain outside the compatibility promise. Add a portable uFor
concept only when it is useful independently of SFZ.

## Priorities by User Interest

This ranks the remaining work by the likely payoff to someone importing and
playing real instruments, not by opcode count or implementation convenience.
The pure mappings belong in uFor; recs supplies local asset facts. An eventual
player or editor owns live MIDI input and playback, not recs.

1. **Keyswitches and controller conditions.** Articulation switching, `loccN`/
   `hiccN`, trigger CC ranges, and initial CC values unlock many real-world
   instrument libraries. Extend the separate performance-binding model and
   portable selection state before mapping them; do not guess how a host reads
   or schedules controllers.
2. **Basic filters and their musical controls.** Cutoff and resonance have a
   large audible effect. uFor now defines resonant filters and enge renders
   them, so map only SFZ responses and ranges with a verified equivalent.
   Then consider key/velocity tracking and filter envelopes or LFOs; diagnose
   responses that are not equivalent rather than approximating them.
3. **Pitch bend and aftertouch.** These make an imported instrument expressive
   under performance. Define their transport-neutral event and binding rules,
   then map the SFZ ranges and modulation targets that those rules can express.
4. **Amplitude and pitch LFOs, plus richer envelopes.** Vibrato, tremolo and
   evolving patches are more compelling than another static mapping. Reuse
   uFor's shared envelope/LFO semantics, including fade-in, and declare any
   SFZ timing or shape mismatch explicitly.
5. **Repeated-note and release behavior.** Repeated-trigger masking and
   release-tail termination matter for drums and realistic legato. Specify
   portable rules beyond the existing voice limits and oldest-immediate
   stealing rule before mapping SFZ controls.
6. **Stereo width and position.** Intermediate width and channel placement
   are useful for stereo samples, but less fundamental than articulation and
   timbre. Keep their native channel semantics independent of SFZ opcode names.
7. **Reproducible random variation.** Random gain, pitch, offset, and delay can
   enliven repeated notes, but need declared random state so renders and
   snapshots remain reproducible.
8. **Equalization.** Map SFZ EQ only after its bandwidth and resonance transfer
   functions are specified and tested against the native EQ model.

Output buses, sends, effects, generated waveforms, and waveguides remain
separate, larger designs rather than prerequisites for the above work.

## Controller Bindings

The separate `performance_binding` score now describes MIDI channel-to-part,
note identity, and named-control CC conversion independently of host adapters.
SFZ import can return it alongside the instrument when the caller explicitly
supplies an instrument reference, part, and repeated-key release rule. Shared
`lochan`/`hichan` ranges map; mixed per-region ranges remain diagnosed.
Other protocols need their own explicit input profile.

The prioritized binding work also includes previous-key conditions and
controller curves. Until each construct has a defined portable representation,
report it as requiring a controller binding.

## Explicit Deferrals

- beat synchronization without a transport and tempo model;
- output buses, sends, and `<effect>` without a routing graph;
- generated waveforms and waveguides without a synthesis-source model;
- random delay, offset, pitch, and gain until reproducible random state exists;
- MD5 assertions unless recs adopts general asset verification;
- vendor extensions, including `#include`.
- player-specific sample-unit interpretations of `sample_fadeout`.

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
- Native uFor additions remain protocol-neutral and independently useful.
- The full suite does not access real MIDI devices.

## Additional work beyond the prompt

None.
