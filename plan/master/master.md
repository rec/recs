# Recs: a common language for things that happen in time

Status: stages 1 and 2 are implemented. The shared-format extraction into
[Ufor](ufor.md) now covers recordings, arrangements, sequences, tunings, scales,
and oscillator definitions. Ufor also implements the first envelope/LFO control
profile, with exact timing and scalar conformance cases. Stage 3 still requires
the native instrument document, source bindings, preparation, and SFZ cutover.
Shared performance events and typed scalar routes are now implemented, with
the [instrument contract](../../../ufor/doc/instrument-format.md) defining the
remaining boundary. Further audio waveform
generation, especially the sampler, is deferred until that design is settled.
The implemented subset is documented in the
[arrangement format](../../doc/arrangement-format.md) and
[recording/sequence format](../../doc/recording-format.md). The broader domain
designs below remain proposals, not a claim of universal playback. See the
[implementation status](how-to.md#implementation-status) and
[Ufor handover](ufor.md) for the completed extraction and remaining work.
Backward compatibility is not a requirement.

Recs should record, edit, compose, and play time-varying quantities and events.
Audio, musical performance, keystrokes, fixture controls, LED fields, voltages,
and timed requests should share documents that humans can read and exchange.
Sample instruments, synthesizers, mixes, and radio shows are reusable objects
in that language. Video is outside this proposal, including video editing and
video codecs. A matrix of LED quantities remains in scope.

## The central decision

Use one document envelope and typed composition model, with distinct payloads
for genuinely different data. A note release is an event; a voltage is a
quantity; a light field also has geometry. Making everything an audio buffer,
a MIDI message, or a dictionary of arbitrary values would discard meaning.

An object exposes typed input and output ports and named parameters. Its
definition can be a recording, sequence, arrangement, sample instrument,
processor graph, or live endpoint. Other objects refer to that public interface.
A mix can contain another mix without knowing its internal tracks. An instrument
can drive audio and lighting through separate, explicitly typed routes.

Keep three things distinct:

1. **Definition:** what the work means, its assets, timing, connections, and
   musical or physical parameters.
2. **Binding:** which installed implementation or physical endpoint will realize
   that definition, including parameter and channel mappings.
3. **Run record:** what actually happened, including clock observations, live
   material, failures, operator actions, and rendered assets.

This is a file format and execution contract, not a replacement plugin ABI,
network protocol, operating system, or database.

## Document map

| Document | Subject |
| --- | --- |
| [Time](time.md) | Exact time, beats, clocks, synchronization, and scheduling |
| [Quantities](quantities.md) | Sampled audio, control curves, CV, gates, and measured features |
| [Events](events.md) | Notes, MIDI, keys, OSC, requests, and sequence semantics |
| [Recordings](recordings.md) | Assets, stream fragments, gaps, capture journals, and packaging |
| [Instruments](instruments.md) | Sample instruments, voices, layers, and performance controls |
| [Processors](processors.md) | Synthesizers, DSP, analysis, and typed processing graphs |
| [Modulation](modulation.md) | Envelope and LFO design before new rendering engines |
| [Arrangements](arrangements.md) | Clips, tracks, buses, automation, and nested mixes |
| [Broadcasts](broadcasts.md) | Future programmes, live sections, live relays, and rebroadcast |
| [Lighting](lighting.md) | Fixture state, DMX/Art-Net, pixel fields, and geometry |
| [Bindings](bindings.md) | Implementations, device profiles, parameter translation, and limitations |
| [Tunings](tunings.md) | Pitch, scales, and the connection to Tuney |
| [How to implement](how-to.md) | Current structures, replacements, ownership, and staged work |
| [Future features](future-features.md) | Candidate work beyond the first usable system |

## A small common vocabulary

The proposed root is `Document`, serialized as TOML. Use `format = "recs"`,
integer `version = 1`, a stable `id`, a human `name`, and `kind` to select the
body. This version is independent of existing recsam and edit versions.
The initial kinds are `recording`, `sequence`, `instrument`, `processor`,
`arrangement`, `broadcast`, `binding`, `layout`, and `tuning`.

The envelope can carry `timebases`, `assets`, `dependencies`, `ports`, and
`parameters` collections, each empty when unused. A required `body` is selected
by `kind` and contains that domain's fields. A processor body may contain a
live endpoint node whose realization requires a binding. A recording exposes
its selected streams as declared output ports. This keeps endpoint references
and recording references consistent with other reusable objects.

| Structure | Required meaning |
| --- | --- |
| `Timebase` | ID and exact rational ticks per second, or ticks per quarter note with a tempo map |
| `StreamType` | Payload family, semantic schema, unit where numeric, shape/layout, and timebase |
| `Port` | Stable ID, direction, stream type, and declared combination rule if it accepts multiple connections |
| `Parameter` | Stable ID, type, unit/domain, default, permitted range or choices, scope, and automation policy |
| `Asset` | ID, relative path, encoding, and payload description; sealed assets also have byte length and SHA-256 |
| `Dependency` | Local ID, relative document path, and digest of the referenced document when sealed |
| `Node` | ID, referenced definition or registered primitive, and parameter values |
| `Connection` | Explicit source node/port and destination node/port references |
| `Binding` | Realization of a definition or endpoint with a declared capability contract |
| `RunRecord` | Definition identity, resolved dependencies/bindings, observations, and produced assets |

Use three stream families: `sampled` for regular arrays, `curve` for timed
numeric knots, and `event` for discrete typed records. Semantic schemas refine
these: audio PCM, pitch estimates, performance events, raw MIDI, fixture state,
and pixel fields have different contracts even when their storage families match.
Static definitions such as layouts and tunings are document dependencies, not
pretend streams with one value per audio frame.

Public ports are the complete interface. A reference to an arrangement reads
its named exported port, never a private bus guessed from a filename. Parameter
addresses use structured `{node, parameter}` references; port addresses use
`{node, port}`. An exported parameter explicitly delegates to one internal
parameter. A macro affecting several parameters is a mapping processor.

IDs are unique in their declared collection and remain stable through display
name edits. Imports are namespaced by dependency ID. Reference cycles between
documents are invalid; signal feedback has separate rules in [Processors](processors.md).
No implicit merging of equally named objects occurs.

## Serialization and editing

TOML holds definitions, small curves, and short authored sequences. Bulk
payloads are assets described in [Recordings](recordings.md). Reuse the same
typed event records in inline `events` and recorded JSONL; these are storage
forms of one model, not different sequence languages. A stream chooses one
storage form. Files are relative to their containing document; portable export
collects dependencies under one directory and rewrites references.

Use tagged Pydantic models with explicit fields, frozen definitions, and list
or dict collections. Keep runtime handles and mutable state out of documents.
Unknown required kinds, operations, or fields are validation errors. Vendor
parameters belong in a typed binding profile, rather than unchecked keys in
the common schema. Opening and editing a definition must not load plugin code,
connect to devices, or execute Python or shell text.

The examples in this directory are proposed TOML fragments unless explicitly
identified as complete. Names such as `recs.gain` describe proposed operation
contracts, not import paths or currently available commands. Complete required
fields and machine-readable schemas are an implementation deliverable in
[How to implement](how-to.md); these documents fix the important semantics first.

## What uniformity promises

A conforming reader can inspect, validate, and edit the definition without its
original devices. A capable host can realize its selected graph. Unsupported
operations remain visibly unsupported; they are not silently omitted or
substituted. A resolved run states which capabilities were required and used.

Identical parameter names do not promise identical sound, color, or timing.
A compressor threshold and ratio do not specify its detector or transfer curve.
For reproducible results, retain a precise implementation binding and initial
state, or capture the produced streams. Distinguish semantic interchange from
reproducing a particular performance.

## Application responsibilities

| Application | Role in the proposed system |
| --- | --- |
| Ufor | Common definitions, pure musical mathematics, codecs, schemas, and portable conformance cases |
| Recs | Capture, asset preparation, timeline editing, verification, and eventual playback transport |
| Lyte | Lighting generators, fixture and geometry interpretation, and physical lighting outputs |
| Streamo | Live stream input/output adapters and broadcast delivery; its existing video features stay outside this format |
| Showco | Installation coordination, bindings, operator controls, and observable run status |
| Tuney | Tuning/scale authoring and experiments; provide explicit pitched performance and synthesis definitions |

The implemented shared definitions live in `~/code/ufor`, published as
[rec/ufor](https://github.com/rec/ufor). Recs and Tuney consume that shared core
through direct imports. Tuney's UI and existing waveform generation, Recs's
capture and file-verification operations, and Reccy's application infrastructure
remain in their own projects. See the [extraction handover](ufor.md) for the
implemented boundary and remaining design work.

## First useful result

Stages 1 and 2 already cover arrangements and native capture. Tuning, scale,
oscillator, envelope, and LFO definitions now have portable Ufor models and
musical or scalar/state conformance cases. The instrument contract now includes
shared performance events and typed routes. Next, implement the coordinated
native instrument and SFZ cutover consuming them. Design the
sampler's interface without selecting its implementation language or producing
new audio. Later rendering and a possible VST realization require the model
gate to pass and a separate implementation decision. Cross-domain control and
broadcast work can reuse existing recordings and engines. Each stage has its
own acceptance gate in
[How to implement](how-to.md).

## Additional work beyond the prompt

None.
