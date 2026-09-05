# Standard SFZ import

## Goal

Extend `recs.recsam.sfz.read()` to import the useful, non-vendor-specific parts
of SFZ 1 and SFZ 2 without silently changing their meaning.

The target is not "every opcode accepted". The target is a lossless,
well-diagnosed import of every SFZ feature that Recs can represent. Every
standard opcode should eventually be either:

1. imported exactly;
2. rejected with a specific explanation and source location; or
3. listed as deferred because Recs lacks a required general concept.

SFZ features should cause additions to recsam only when those additions are
useful outside SFZ. Recsam should not become an SFZ player disguised as a file
format.

## Scope

Use the version labels in the [SFZ opcode catalogue](https://sfzformat.com/opcodes/)
as the scope boundary. Include opcodes marked SFZ v1 or SFZ v2. Exclude opcodes
marked ARIA, Cakewalk, sfizz, LinuxSampler, Calfbox, rgc, or another
implementation name.

This has one counterintuitive consequence: `#define` is SFZ 2 and is in scope,
but the commonly used `#include` directive is documented as an ARIA extension
and is not. It may be reconsidered separately if importing real-world libraries
proves more important than the non-vendor boundary.

The importer should retain its current all-or-nothing API:

```python
def read(path: Path) -> SampleInstrument:
```

It must not ignore unsupported headers or opcodes. A successful return means
that all material behavior in the source has been represented.

## Why complete SFZ compatibility is undesirable

SFZ is a family of related player behaviors rather than a sufficiently precise
interchange specification. Some supposedly standard features differ between
players, including sequence counters, random selection, release triggering,
loop crossfades, and handling of sample metadata. Accepting their spelling does
not guarantee compatible playback.

Several SFZ concepts also conflict with deliberate recsam boundaries:

- MIDI channel numbers, CC numbers, key switches, pitch bend, and aftertouch
  are controller bindings, not properties of a transport-neutral sample
  instrument.
- Beat-synchronised playback needs a transport and tempo model.
- Output buses, sends, and `<effect>` need a processing and routing graph.
- Filters need their own design, including type definitions and modulation
  behavior.
- Generated oscillators and waveguides are synthesis sources, not sample slots.
- Random delay, offset, pitch, and gain need a reproducibility policy.

Implementing these directly in the importer would either leak MIDI and SFZ
player assumptions into recsam or produce files whose apparent precision is
misleading. They should remain explicit errors until the corresponding general
Recs feature exists.

## Phase 0: correct existing imports

Before adding breadth, correct cases where the current importer accepts input
but may not preserve its behavior.

### Velocity response

SFZ applies `amp_veltrack=100` by default. The current importer maps velocity
ranges but does not import that amplitude response, making quieter MIDI
velocities play too loudly. Add the standard velocity curve and support
`amp_veltrack` plus `amp_velcurve_N` as a recsam modulation curve.

Define explicitly that SFZ integer velocities are sampled points in the recsam
normalized trigger domain. Avoid claiming exact behavior between those 128
points unless the trigger binding quantizes to MIDI 1.0 velocity first.

### Asset-dependent defaults

Read audio metadata while importing when behavior depends on the asset:

- An omitted `loop_mode` may activate loop markers embedded in the sample.
- `pan` has different meaning for mono and stereo samples. Map mono balance to
  recsam pan and stereo balance to `stereo_balance`.
- Validate channel-dependent operations against the actual sample layout.

Missing or unreadable assets must produce a path-specific import error, not a
guessed interpretation.

### Envelope shapes

SFZ amplitude envelopes do not use recsam's all-linear default shape. Express
the standard attack, decay, and release curves explicitly. Verify the precise
curve definitions before encoding them; reject the envelope if recsam cannot
represent the specified response.

### Trigger and loop semantics

Compare SFZ `release` and `release_key` with recsam `release` and
`logical_release`, particularly while a sustain pedal is held. Likewise compare
`loop_continuous` and `loop_sustain` with recsam `through_release` and
`until_release`, including playback after leaving the loop. Rename or extend
recsam only if the concepts are genuinely different.

### Notes and ranges

Confirm the SFZ defaults for `lovel`, `hivel`, omitted key bounds, and pitch key
centres from versioned references. Document that named notes use the importer's
fixed C4=60 convention because host octave labels are not portable; numeric note
values remain unambiguous.

## Phase 1: parser and diagnostics

Build a complete opcode registry before implementing more conversions. Each SFZ
1 or SFZ 2 header and opcode receives one classification:

- `supported`;
- `needs_asset_metadata`;
- `needs_recsam_model`;
- `needs_controller_binding`;
- `deferred_player_semantics`; or
- `vendor_extension`.

Use this registry to report every unsupported construct in one parse, with the
file path, line, header, opcode, and reason. Syntax errors may still stop parsing
when later tokens cannot be interpreted reliably.

Add the standard SFZ 2 `#define` preprocessor directive. Expansion must happen
at token values, preserve source locations for diagnostics, reject recursive or
undefined variables, and avoid general textual or Python-like evaluation.

Preserve declaration order and inheritance through `<global>`, `<master>`,
`<group>`, and `<region>`. Add `<curve>`, `<effect>`, and `<sample>` to the
registry even while their semantics remain deferred, so they produce precise
errors rather than unknown-header failures.

## Phase 2: features representable now

Implement these in separate, focused changes after Phase 0.

### Crossfades

Map the standard key and velocity crossfade opcodes to recsam layer crossfades:

- `xfin_lokey`, `xfin_hikey`, `xfout_lokey`, `xfout_hikey`;
- `xfin_lovel`, `xfin_hivel`, `xfout_lovel`, `xfout_hivel`;
- the standard crossfade curve selector where its shape has an exact recsam
  counterpart.

Keep discrete selection bounds separate from crossfade bounds.

### Ordered and random variants

Map `seq_length` and `seq_position` to recsam cycle selection after defining
whether the counter advances before or after other eligibility tests. Reject
files whose intended counter grouping cannot be represented.

Map `lorand` and `hirand` only when regions form a complete, non-overlapping
partition and recsam can preserve coherent selection across layered microphone
samples. Do not independently randomize layers that SFZ intended to play
together.

### Static modulation

Use recsam modulation curves for standard mappings whose source is already part
of its trigger model:

- `amp_keytrack` and its key centre;
- general `pitch_keytrack`, not only 0 and 100;
- `pitch_veltrack`;
- standard key- and velocity-dependent amplitude envelope times.

`pitch_random`, `amp_random`, and random timing remain deferred until Recs has a
reproducible randomness model.

### Playback details

Import exact, transport-independent controls where the model already supports
them, including aliases and versioned defaults for sample start, sample end,
loop points, gain, tuning, transposition, direction, trigger, and exclusive
groups. Keep SFZ's inclusive frame endpoints converted to recsam's half-open
intervals in one documented helper.

## Phase 3: general recsam model additions

Design and implement each model feature independently of the SFZ importer, then
add its SFZ conversion. Do not add SFZ-named fields to recsam.

### Loop behavior

Add loop direction independently of whole-sample direction so SFZ 2
`loop_type=forward`, `backward`, and `alternate` can be represented. Consider
loop count and loop crossfade only after defining exact endpoint and transition
behavior. Player-dependent crossfade behavior must not be guessed.

### Voice lifecycle

Add general concepts for instrument, note, and group voice limits; voice
stealing; repeated-note self-masking; and release-tail termination. These can
then represent standard `polyphony`, `note_polyphony`, `note_selfmask`, and
`rt_dead`. Preserve the already supported `group`, `off_by`, and `off_mode`.

### Playback window and channel processing

Consider general fields for delayed start, repeat count, end fade, stereo width,
channel position, channel swap, and polarity inversion. These can represent the
corresponding SFZ playback and spatial controls without embedding SFZ terms.

### Modulation envelopes and LFOs

Add only missing general capabilities, such as LFO fade-in, needed by the
standard amplitude and pitch LFOs. Map standard pitch envelopes and amplitude
LFOs to named recsam modulation routes. Filter envelopes and filter LFOs remain
blocked on the filter design.

### Equalization

Investigate an exact conversion from SFZ equalizer bandwidth in octaves to the
recsam peaking-band resonance value. Validate the transfer functions at the
configured sample rate. Import `eqN_freq`, `eqN_bw`, and `eqN_gain` only if this
conversion is exact enough to specify and test; otherwise treat SFZ EQ with the
filter work.

## Phase 4: controller bindings

Do not add MIDI-specific fields to `SampleInstrument`. First design a companion
binding document that maps MIDI and other control protocols onto recsam's named
events and controls. An SFZ import which contains bindings would then emit both
the instrument and its binding, which requires a new API rather than changing
the meaning of `sfz.read()`.

That later importer may cover:

- MIDI channel ranges;
- continuous-controller conditions and modulation;
- pitch bend ranges and steps;
- channel and polyphonic aftertouch;
- key switches and previous-key conditions;
- initial controller values from `set_ccN`;
- controller curves declared with `<curve>`.

Until that API and file format exist, reject these opcodes as requiring a
controller binding.

## Explicit deferrals

The following standard SFZ areas should be classified but not implemented by
this plan:

- filters, filter envelopes, and filter LFOs, pending the dedicated filter
  design;
- beat synchronization, pending a transport and tempo model;
- output buses, sends, and `<effect>`, pending a routing graph;
- `<sample>` generated waveforms and waveguides, pending a source synthesis
  model;
- random delay, offset, pitch, and gain, pending deterministic random-state
  semantics;
- MD5 asset assertions, unless Recs adopts content verification generally;
- vendor extensions, including `#include`, by definition of this plan's scope.

## Implementation sequence

Each numbered item should leave the importer and tests passing and should be one
commit unless its recsam model change and importer change need separate commits.

1. Add the complete standard-opcode classification and aggregate diagnostics.
2. Correct velocity response and add velocity-curve import.
3. Make loop defaults and spatial mapping asset-aware.
4. Correct envelope, trigger, loop, note, and range semantics.
5. Add SFZ 2 `#define` parsing.
6. Add key and velocity crossfades.
7. Add ordered selection with documented counter behavior.
8. Add random selection only for provably coherent region groups.
9. Add the currently representable static modulation opcodes.
10. Propose and review each Phase 3 recsam model addition before implementing
    its corresponding SFZ family.
11. Design controller bindings before accepting any MIDI-specific opcode.
12. Publish a generated support table from the opcode registry so code and
    documentation cannot drift independently.

## Tests

Use small, hand-written SFZ fixtures with regression snapshots of the resulting
`SampleInstrument` and diagnostics. Cover:

- header inheritance and declaration order;
- every supported opcode's defaults, bounds, and units;
- inclusive SFZ frame endpoints converted to half-open recsam intervals;
- mono, stereo, embedded-loop, and missing sample assets;
- all standard unsupported opcodes producing their classified reason;
- vendor opcodes remaining rejected;
- `#define` expansion, shadowing, undefined names, and recursion;
- coherent cycles and random groups across layered regions;
- trigger, sustain, envelope, and loop-tail behavior;
- malformed input retaining accurate source locations.

Any audio fixtures must be WAV files at 48,000 samples per second and at least
one second long. Where the SFZ reference does not define behavior precisely
enough for a fixture, record that as a deferral rather than selecting one
player's behavior silently.

## Completion criteria

- Every non-vendor SFZ 1 and SFZ 2 header and opcode is classified.
- Every successful import preserves all behavior represented by its source.
- No unsupported opcode or header is silently ignored.
- Errors identify every unsupported construct and explain the missing Recs
  concept.
- Recsam additions are named and specified independently of SFZ.
- The public support table is generated from the same registry used by the
  importer.

## Additional work beyond the prompt

None.
