# Ufor extraction handover

## Incomplete

Portable preparation and performance-action traces, sparse tunings and MTS
byte import, oscillator lifecycle integration, and MIDI 2.0/UMP interchange
remain model work. No sampler, waveform renderer, plugin host, or VST exists.

## Completed

The initial extraction is complete across `~/code/ufor`, Recs, and Tuney.
The public repository is [rec/ufor](https://github.com/rec/ufor); all Git remotes
use SSH. Recs pins a public Ufor source archive at
`7a6d3e44ddd194062243e4e6374f37cac5d7219e` for native instruments and pure SFZ
conversion. Tuney retains its initial extraction pin at
`9fa9d39f356613285e4ec5e55bdb3d894bfd8dbf`. These archives let installations and
release builds run without GitHub SSH credentials. UV development sources use the editable
`../ufor` checkout. Dependency changes are committed separately from code.

## Ownership

| Owner | Implemented responsibility |
| --- | --- |
| Ufor | Timebases, assets, references, stream/encoding types, events, recordings, sequences, arrangements, document codec and schema |
| Ufor | Frequency/ratio expressions, computed tuning, finite frequency and ratio tables, repeating ratios and adjacent intervals, Scala text conversion, scale naming, accidentals, and oscillator parameters/gain |
| Ufor | Segmented envelope and LFO documents, exact control-clock coordinates, event/state calculations, scalar shape/curve observations, and modulation conformance cases |
| Ufor | Shared performance events in native sequences/JSONL; typed parameter/source/route declarations and scalar route evaluation |
| Ufor | Native sample-instrument documents, asset slices, explicit channel maps, controls/selection/chokes/articulations/EQ, generator bindings, and pure SFZ conversion |
| Ufor | Lossless VL70m MIDI 1.0 SysEx inspection and bounded patch relocation, retaining opaque message spans and duplicate occurrences |
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
[JSON Schema](../../../ufor/schema/scores.json), and
[language-neutral conformance cases](../../../ufor/conformance/pitch.json)
live with the implementation. The common codec handles recording, sequence,
arrangement, tuning, scale, oscillator, envelope, LFO and instrument documents. The
[modulation profile](../../../ufor/doc/modulation-format.md) specifies the new
control models now used directly by sample instruments. Recs now imports performance
events directly from `ufor.events`; its old `recs/recsam/events.py` is removed.
The [instrument contract](../../../ufor/doc/instrument-format.md) specifies
the implemented native instrument/SFZ cutover and its remaining preparation
boundary. All portable Recsam definitions and pure SFZ conversion now live
in Ufor; Recs retains only asset and SFZ file acquisition.

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
The VL70m proof of concept is intentionally MIDI 1.0 byte-stream only. UMP,
native MIDI 2.0 messages, SysEx8, MIDI-CI, Profiles, and Property Exchange need
their own transport and capability design before Ufor adds further
device-specific MIDI descriptions.

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
The performance/route milestone passes 192 Ufor tests and 865 Recs tests,
plus those static checks. Thirty shared event tests moved from Recs into Ufor;
Recs retains instrument-specific event validation tests. Tuney was not changed
or retested in this milestone.
The completed Recsam consolidation passes 306 Ufor tests and 741 Recs tests,
plus Ruff, formatting, type checking, pyupgrade and diff checks. The wheel
contains all 35 Python modules. Pure musical/model tests now live in Ufor;
Recs retains SFZ file/asset integration tests, including byte-preserving import
and symlink containment. No production media was touched in this consolidation.
Ufor has no GitHub workflows, as requested. Automated checks do not
claim live hardware or packaged application validation.

Both production recordings were verified again with Ufor-owned models. The
short recording has five MIDI files; the full one has 56 audio files and five
MIDI files. Media and original journals were unchanged. The full recording's
39 unresolved audio placements remain explicit and are still rejected when
selected for timeline editing. This extraction preserves the `format = "recs"`
marker and version 1, so it requires no new production metadata migration.

## What remains

The first envelope/LFO profile, shared performance events, typed routes, native
instrument root, slices, channel maps, source bindings and SFZ conversion are
implemented. Next define resolved preparation settings and portable
selection/gate/retirement action traces. These stateful components never existed
in Recsam and are not part of the completed type consolidation. Sparse tuning
maps, Scala keyboard mapping, MTS byte import, audio oscillator lifecycle
integration, the MIDI 2.0/UMP interchange layer, and richer cross-domain graphs
remain future model work. No sampler engine,
new waveform renderer, compiled-language implementation, or VST was added.
Existing implementations can realize later contracts after an explicit design
and conformance decision. Stage 3 as a whole is not yet complete.

## Additional work beyond the prompt

None.
