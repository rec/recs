# Pitch, tunings, and scales

Part of the [master proposal](master.md). Revised 8 September 2026.
Pitch, a tuning degree, and a sample-selection key are separate coordinates.
Tuney's musical model is the starting point for shared definitions; its
instrument fallback behavior does not define the portable tuning's domain.

The [initial Ufor extraction](ufor.md) implements the four source forms below
with contiguous finite tables. The noncontiguous example and broader mapping
requirements in this proposal remain future model work. The implemented wire
fields and expression grammar are specified in
[Ufor's musical format](../../../ufor/doc/musical-format.md).

## Repetition is musical data

Support both repeating and finite definitions, including finite frequency
ratios relative to a reference frequency. Do not infer repetition merely because
values form a list, or because an instrument must respond to every input key.

| Definition | Meaning outside the listed range |
| --- | --- |
| Repeating adjacent-ratio pattern | Continue multiplying successive intervals, including inverse traversal below the reference degree |
| Repeating reference-ratio cycle | Repeat degree ratios with an explicit frequency multiplier for each cycle |
| Finite ratio table | Only declared degrees exist; each ratio is relative to the declared reference Hz |
| Finite frequency table | Only declared degrees exist, with explicit positive Hz values |

These are distinct semantics to capture in a compact discriminated model during
stage 3. Adjacent ratios describe successive intervals; reference ratios describe
positions relative to an origin. A reader must never guess which a list means.
The earlier equal-division representation can be authoring shorthand for a
repeated single interval rather than another independently maintained model.

Separate **pattern length in steps** from **frequency multiplier per cycle**.
Western 12-tone equal temperament has a one-step repeating interval
`2^(1/12)`. Its one-step multiplier is also `2^(1/12)`; twelve steps give `2`.
A twelve-step just-intonation pattern may have twelve adjacent ratios
whose product is `2`. Neither pattern length nor multiplier is necessarily 12
or an octave. Do not force all just-intonation scales to have twelve steps.

For adjacent ratios `r[0] ... r[N-1]`, define
`f(k+1) / f(k) = r[k mod N]` relative to the reference degree. The cycle
multiplier is the product of those ratios, not a second independently editable
value. For reference ratios `q[i]` and cycle multiplier `P`, define
`f(a*N+i) = reference_hz * P^a * q[i]`, with `0 <= i < N`, `q[0] = 1`,
and degree zero at the reference. Specify Euclidean division for negative
degrees so implementations in different languages agree.

Illustrative finite ratio entries, with no wrapping:

```toml
representation = "ratio_table"
reference_hz = "440"
entries = [
  { degree = -1, ratio = "2/3" },
  { degree = 0, ratio = "1" },
  { degree = 1, ratio = "5/4" },
]
```

Degree 1 is 550 Hz; degree 2 is undefined. Frequency and ratio values are
positive, but a ratio below one is valid. A finite table need not be ascending
or contiguous. Undefined pitch remains explicit during validation/preparation.
Any instrument decision to substitute a playable note belongs to a separate,
visible mapping policy, not to modulo indexing in the tuning definition.

## Human-readable frequency and ratio expressions

Adopt the user's frequency/ratio minilanguage, a superset of Scala pitch-value
notation. Fractional authoring such as `5/4` and `2/3` is a requirement, not an
optional display convenience. `/` means division and `^` means exponentiation.
Keep exact rational arithmetic where possible; retain powers such as the
equal-tempered interval symbolically until numerical evaluation is needed.
Do not require composers to replace fractions with decimal approximations or
numerator/denominator object syntax.

TOML expression values are quoted strings. Frequency fields supply the Hz
context; ratio fields supply a dimensionless context; Scala cents values must
keep their cents meaning. A cents offset has ratio `2^(cents/1200)` regardless
of tuning step size. Parsing yields typed values or expression nodes, not
executable Python. The authored expression is authoritative; numerical results
are derived values with a stated evaluation precision.

Before implementing the parser, document the actual minilanguage's complete
grammar, precedence, associativity, grouping, signs, whitespace, and decimal
rules. `2^(1/12)` above makes the intended grouping explicit. In particular,
distinguish Scala's decimal-cents syntax from a decimal ratio or Hz value by
the declared value kind/import context. Preserve Scala inputs' meaning rather
than treating their decimals as ordinary ratios. Publish accepted and rejected
examples, zero-denominator handling, and positive finite-result requirements.
Do not invent unspecified operators while extracting the existing language.

Tuney's currently inspected `scale/evaluate.py` uses Python AST arithmetic and
math/random calls. It is not evidence that the requested `/` and `^` language
is already implemented there. Locate and reconcile the user's minilanguage
before porting a parser; Python `^` must not acquire XOR semantics. The portable
frequency language does not inherit arbitrary functions, randomness, or Python
evaluation from Tuney's broader expression UI.

## Scala and MIDI interchange

Scala is a primary tuning interchange target. Preserve its ratio/cents entries,
implicit unison, and final period entry, translating to explicit repeat
semantics. A Scala list contains offsets from unison, not adjacent interval
ratios; converting to adjacent ratios requires successive quotients. Keyboard
mapping and reference frequency are separate from that scale data. See the
[Scala scale-file specification](https://huygens-fokker.org/scala/scl_format.html).

MIDI Tuning Standard per-key frequency tables are finite mappings and must not
gain automatic repetition. The MTS Scale/Octave extensions also support
repetition; handle that explicitly in their adapter rather than assuming all
MTS messages describe the same kind of tuning. See the
[MIDI Association's tuning specification summary](https://midi.org/midi-tuning-updated-specification).
Report interchange rounding and unsupported expressions. Exporting a finite
table to a repeating format requires an explicit musical decision.

## Scales and performance

A scale selects and names degrees from a tuning. Preserve Tuney's selection,
spelling, accidentals, offsets, reference frequency, and detuning semantics.
Keyboard mappings and educational presentation do not change the underlying
frequency definition. Avoid baking MIDI's key range into the common degree type.

Authored performance events reference tuning degrees and documents. Preparation
resolves them to one authoritative `pitch_hz`; retain authored degrees as
provenance. A frequency measurement already in Hz needs no scale assignment.
Specify whether pitch bend acts before or after retuning, with explicit scope
and range. Repeated same-key triggers retain independent identities.

Sample playback relates event frequency to the slot's reference frequency;
oscillators consume Hz. MIDI and CV bindings report quantization and limitations
on independent pitches. These contracts can be designed and checked without
generating audio or implementing a sampler.

## Extraction and acceptance

Extract musical definitions and pure calculations from Tuney's `Tuning`,
`Computed`, `Ratios`, `Table`, and `Scale`. Keep UI annotations, file dialogs,
and fallback selection local. `Table.__call__` currently uses modulo indexing
to keep Tuney's instrument playable; that is explicitly not the finite-table
contract. Review the host mapping when adopting the new model rather than
silently copying that fallback or changing Tuney in this planning revision.

Use language-neutral fixtures for exact fractions, fractional powers, a
one-step equal-tempered pattern, a twelve-step just-intonation example,
non-octave cycles, negative degrees, finite ratio/Hz boundaries, Scala import,
and MTS per-key tables. Preserve Tuney examples where they express intended
musical behavior; identify intentional corrections separately. Define numeric
tolerances for irrational results. Parser, model, and pitch-value tests come
before any new waveform generation.

## Additional work beyond the prompt

None.
