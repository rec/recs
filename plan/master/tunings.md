# Pitch, tunings, and scales

Part of the [master proposal](master.md). Pitch is not a MIDI note number, and
a sample-selection key is not necessarily pitch. Keep these distinctions
throughout instruments, sequences, analysis, and physical control mappings.

## Tuning definitions

A tuning document defines a pitch coordinate system and its mapping to positive
frequencies. Use one tagged representation per definition:

- `equal_division`: number of divisions and a positive repeating frequency
  ratio, with reference degree and reference Hz.
- `ratios`: ordered positive rational ratios within a declared repeating period,
  with reference degree and reference Hz.
- `frequency_table`: explicit degree/frequency entries; no implied repetition
  or interpolation outside those entries.

A scale selects and names degrees from a tuning. Its spelling, accidentals,
keyboard mappings, and educational presentation do not change the underlying
frequency definition. Non-octave repetition is valid. A cents offset has the
fixed ratio `2 ** (cents / 1200)`; a step in a tuning is a separate quantity.

Illustrative equal-division tuning body:

```toml
representation = "equal_division"
divisions = 19
period_ratio = { numerator = 2, denominator = 1 }
reference_degree = 0
reference_hz = 440.0
```

Degree 19 is 880 Hz; degree 1 is `440 * 2 ** (1/19)` Hz. Preserve rational
ratios as numerator/denominator pairs where specified rather than rounding them
into decimal strings. General formula evaluation is not needed for these
initial representations.

## Performance and realization

Authored musical events can reference tuning degree and tuning document.
Preparation resolves those to `pitch_hz` for the performance stream. A resolved
event has one authoritative pitch; retain its authored degree as provenance,
not a second competing pitch instruction. A recorded frequency measurement
already in Hz need not be forced onto a scale.

Pitch bend is a typed relative pitch control with defined scope. Decide whether
it applies before or after a retuning mapping in the graph. Do not infer bend
range from a MIDI device's customary setting. Per-note retuning must preserve
trigger identity, including two simultaneous instances of the same key.

Sample playback relates event frequency to the slot's reference frequency.
Oscillators consume Hz. A MIDI or CV output binding translates to its device's
capabilities and reports quantization, range limits, or unsupported independent
pitch control. A device with fewer independent pitch channels cannot realize
arbitrary polyphony by changing parameter units alone.

## Change from today

Tuney already has `Tuning`, `Computed`, `Ratios`, `Table`, and `Scale` in
`tuney/scale/`. Reuse the mathematics and examples, but keep its UI annotations,
callable runtime behavior, and fallback selection out of portable definitions.
Its `Tuning.active` selects among optional representations; the new document
chooses exactly one with a discriminator. Export a concrete tuning result for
any computation not yet covered by the initial vocabulary.

Recsam's `Mapping.reference_pitch_hz` and `Trigger.pitch_hz` already support
separating selection from pitch. Preserve that design. The new common tuning
dependency fills in authored musical meaning, rather than putting MIDI-specific
pitch assumptions back into the sampler.
