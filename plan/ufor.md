# uFor

## Purpose

uFor is the portable definition layer for things that happen in time. It owns
the immutable, validated meaning of scores, not their application-specific
realization. Its Python package supplies frozen Pydantic models, TOML codecs,
generated JSON Schema, exact reference calculations, and language-neutral
conformance cases that another implementation can adopt without copying Python
class layouts.

uFor does not own audio-device access, file acquisition, rendering loops,
transport deadlines, GUI state, MIDI/OSC endpoint connections, plugin loading,
or output encoding. An explicit library reader may load declared local score
files, but portable definitions do not carry host paths, loaded buffers,
connections, or runtime state.

## Current implementation

The repository at `~/code/ufor` currently provides:

- common score headers, exact rational timebases, sealed assets, structured
  references, stream/encoding descriptions, named ports, parameters, and TOML
  and JSON Schema interchange;
- recording, event-stream, sequence, arrangement, composition, binding,
  broadcast, slideshow, fixture, and light-animation definitions;
- exact pitch expressions, tunings, scales, Scala conversion, oscillator
  definitions, envelopes, LFOs, typed modulation routes, and scalar automation;
- shared `Trigger`, `Release`, and `ControlChange` events with exact ticks,
  ordinals, scoped controls, independent trigger identities, and explicit
  release matching;
- sample-instrument scores with sealed asset slices, key/velocity mappings,
  loops, explicit channel routes, controls, selections, chokes, articulations,
  processing declarations, deterministic variation, and lifecycle traces;
- synth-instrument scores, synth lifecycle traces, and voice settings that
  reuse the portable oscillator, envelope, LFO, modulation, routing, and
  performance models; and
- pure SFZ parsing, compilation, export, and precise unsupported-feature
  diagnostics, plus bounded VL70m MIDI 1.0 SysEx inspection and relocation.

The defining documentation and portable cases live alongside the package, in
`~/code/ufor/doc/`, `~/code/ufor/schema/`, and `~/code/ufor/conformance/`.
The cases, rather than a particular runtime implementation, are the portable
acceptance boundary.

## Ownership boundaries

| Project | Responsibility |
| --- | --- |
| uFor | Portable definitions, validation, codecs, schema, exact mathematical/state references, preparation and lifecycle traces, and conformance cases |
| recs | Capture, sealed local asset facts, session migration, editing, export, SFZ file acquisition, and existing audio rendering |
| tuney | Authoring/UI policy, instrument-range mapping, broader expressions, Scala file access, MIDI delivery, and its existing waveform-host behavior |
| enge | Engine-only realization of prepared uFor actions into bounded audio buffers |
| lyte | Lighting-host state, drivers, installation-specific patching, and physical delivery |
| streamO and showCo | Operational streaming, transport, service, and run responsibilities |
| reccy | Shared Python application infrastructure, with no portable-format ownership |

uFor must not grow adapters that silently choose host policies. For example,
an SFZ file adapter supplies measured asset metadata, a host resolves raw MIDI
to performance events, and an engine consumes prepared actions. None of those
operations belongs in a portable score parser.

## Instrument boundary

uFor owns instrument meaning and state-action preparation, but not waveform
generation. Sample and synth scores are sibling definitions that consume the
same performance events and lifecycle rules. The sample trace establishes
selection, sustain, logical release, choke, retirement, voice limits, and
variation before any engine renders audio. The synth trace supplies equivalent
voice starts and retirements to enge's narrow reference renderer.

The current model therefore permits an engine to reject unsupported profiles
without changing score semantics. It does not authorize a sampler, general DSP
graph executor, plugin host, VST wrapper, or live host inside uFor.

## Next agent guidance

Start a uFor change from a concrete portable semantic need, not from an
application class or a backend convenience. Before implementation, specify:

1. the authored fields, defaults, units, exact ordering, scope, and failure
   behavior;
2. preparation output and mutable-state ownership, if the feature is stateful;
3. TOML codec and JSON Schema behavior; and
4. language-neutral conformance examples, including rejected cases and any
   numeric tolerance.

Then update consuming applications in separate, coherent cutovers. Do not add
re-export compatibility layers or preserve retired application models merely to
avoid migration work.

Remaining portable model decisions include sparse/noncontiguous tuning maps,
Scala keyboard mappings, MTS byte import and sparse updates, the full MIDI
2.0/UMP interchange, looped envelopes, random/sample-and-hold generators,
continuous LFO rate ramps, modulation feedback, and richer cross-domain graph
semantics. Each is independent work, not an implied extension of the current
instrument renderer.

See [the uFor extraction handover](master/verification-procedures.md#ufor-extraction-handover),
[the instrument contract](../doc/sample-format.md), and
[the offline engine boundary](enge.md) for the surrounding plan.

## Additional Work Beyond The Prompt

None.
