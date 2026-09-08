# Ufor extraction handover

The initial extraction is complete across `~/code/ufor`, Recs, and Tuney.
The public repository is [rec/ufor](https://github.com/rec/ufor); all Git remotes
use SSH. Application dependencies pin a public source archive to commit
`9fa9d39f356613285e4ec5e55bdb3d894bfd8dbf`, so installations and release builds
do not require GitHub SSH credentials. UV development sources use the editable
`../ufor` checkout. Dependency changes are committed separately from code.

## Ownership

| Owner | Implemented responsibility |
| --- | --- |
| Ufor | Timebases, assets, references, stream/encoding types, events, recordings, sequences, arrangements, document codec and schema |
| Ufor | Frequency/ratio expressions, computed tuning, finite frequency and ratio tables, repeating ratios and adjacent intervals, Scala text conversion, scale naming, accidentals, and oscillator parameters/gain |
| Ufor | Segmented envelope and LFO documents, exact control-clock coordinates, event/state calculations, scalar shape/curve observations, and modulation conformance cases |
| Recs | Capture, journals, finalization, verification, media I/O, session migration, editing and existing rendering |
| Tuney | Editable configuration and UI annotations, units and broader expressions, Scala file/browser access, instrument-range wrapping, MIDI protocol delivery, and existing NumPy waveform generation |
| Reccy | Shared Python application infrastructure, with no ownership of the portable format |

The old `recs.model` implementations are removed. Direct imports use the defining
`ufor` module, including `ufor.encoding.Format` and `Subtype`. The core model
tests moved to Ufor; Recs retains its application integration tests. Tuney's
Scale and Oscillator classes add UI fields/runtime realization to Ufor models;
its computed/ratio/table/tuning configurations compile to Ufor definitions.

## Documents and musical semantics

[The musical specification](../../../ufor/doc/musical-format.md),
[JSON Schema](../../../ufor/schema/documents.json), and
[language-neutral conformance cases](../../../ufor/conformance/pitch.json)
live with the implementation. The common codec handles recording, sequence,
arrangement, tuning, scale, oscillator, envelope, and LFO documents. The
[modulation profile](../../../ufor/doc/modulation-format.md) specifies the new
control models and their eventual Recsam cutover. Consumer release archives
remain pinned to the initial extraction above; sibling development sees the
new Ufor definitions. Update the archive pin as part of the instrument cutover
when application code begins importing those definitions.

Frequency tables never wrap. Tuney explicitly wraps keys within an instrument's
configured range before consulting its finite definition. Ratio tables are
finite unless they declare a repeat multiplier. Adjacent interval patterns
declare whether they repeat; one `2^(1/12)` interval is a one-step equal-tempered
pattern. Fractions such as `5/4` and `2/3` remain valid human-readable values.

The portable grammar supports numbers, division, powers, signs and parentheses.
It records the user's stated `/` and `^` behavior; no separate original grammar
implementation was found. Tuney retains its broader math authoring language and
also accepts `^`. Scala imports distinguish integer ratios from decimal cents.
Finite MTS tables have an explicit representation, but MTS byte decoding and
sparse update messages are not part of this extraction.

`Computed.limit` retains its actual maximum-denominator behavior. The earlier
Tuney comment calling it N-limit just intonation was inaccurate. Oscillator
gain retains its twelve-key-step convention independently of tuning period.

## Installation and verification

For sibling development, clone Ufor beside Recs and Tuney, then run `uv sync`
in each application. Ordinary package installations use the pinned public
archive; `UV_NO_SOURCES=1` release builds also use it. The archive was tested in
an isolated environment with no Recs, Tuney, Reccy, NumPy, audio, or GUI packages.

Checks passed: 65 Ufor tests, 892 Recs tests, and 513 Tuney tests, plus Ruff,
formatting, type checking and Python syntax modernization. Existing audio
regressions remain unchanged. These counts describe the initial extraction;
the subsequent modulation milestone passes 132 Ufor tests, including 67 new
modulation checks, plus Ruff, formatting, type checking, and pyupgrade.
Ufor has no GitHub workflows, as requested. Automated checks do not
claim live hardware or packaged application validation.

Both production recordings were verified again with Ufor-owned models. The
short recording has five MIDI files; the full one has 56 audio files and five
MIDI files. Media and original journals were unchanged. The full recording's
39 unresolved audio placements remain explicit and are still rejected when
selected for timeline editing. This extraction preserves the `format = "recs"`
marker and version 1, so it requires no new production metadata migration.

## What remains

The first envelope/LFO event and state model is implemented. Next settle the
small instrument/performance contract, including modulation routes, before
replacing the recsam instrument types and adapters together. Sparse tuning
maps, Scala keyboard mapping, MTS byte import, audio oscillator lifecycle
integration, and richer cross-domain graphs remain future model work. No sampler engine,
new waveform renderer, compiled-language implementation, or VST was added.
Existing implementations can realize later contracts after an explicit design
and conformance decision. Stage 3 as a whole is not yet complete.

## Additional work beyond the prompt

None.
