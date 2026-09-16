# Instrument playback boundary and acceptance

## Status and scope

Updated 16 September 2026. The former pause on waveform generation and the
requirement to add a synth definition first are historical gates, now superseded.
uFor supplies sample and synth definitions, preparation, lifecycle traces, and
portable conformance cases. enge is the shared synth and sampler engine project.
Its synth reference exists; sample traversal remains implementation work there.

The two enge goals remain explicit: consolidate reusable tuney synthesis and
implement the corresponding sampler. See [the enge handover](enge.md) for
ownership and [enge's execution contract](../../enge/plan/engine-execution.md)
for its current engine design. Neither a recs sampler nor a second tuney synth
implementation should be created.

This document defines recs' host boundary and acceptance requirements. It does
not authorize new host integration, device runs, plugin support, or backend
selection. Engine implementation status belongs to
[enge's README](../../enge/README.md), not to copied inventories in recs.

## Offline instrument contract

There are two distinct boundaries, not one renderer accepting raw events:

| Owner | Input | Output |
| --- | --- | --- |
| uFor preparation and performance state | Validated instrument and normalized performance events | Prepared definitions and ordered lifecycle/control actions |
| enge engine | Prepared definitions, immutable sample data where applicable, and actions at exact output frames | Bounded audio buffers and restorable engine state |
| recs host | Documents, session assets, transport data, and explicit output settings | Scheduled engine calls, encoded output, provenance, and finalized recording documents |

uFor owns selection, trigger identity, sustain/logical release, chokes, voice
limits, and deterministic variation. enge realizes those decisions as sound;
it must not independently reconstruct pedal or selection policy. Hosts adapt
MIDI/OSC to the normalized event contract and resolve timing to output frames.
Key selection and target pitch remain independent.

The engine advances over half-open frame intervals. Actions at a boundary apply
before its first sample; equal-frame actions retain their declared order.
Contiguous block partitions must preserve actions, audio within the declared
tolerance, and ending state. Snapshots must retain all voice, phase, envelope,
control-smoothing, and traversal state required for equivalent continuation.
Stopping must not invent physical-release events.

The current enge reference returns float64 arrays in `(frames, channels)` order.
The older planar-output proposal is superseded. Hosts should use the published
engine API rather than impose another buffer layout or raw-event interface.
Engine sample decoding and immutable asset preparation may happen before
rendering; file discovery, encoding, devices, and transport remain host work.
No file access or decoding belongs in a render callback.

## recs offline host work

Host integration remains separate work. It should read sealed session assets,
adapt recorded performance input, resolve exact output-frame positions, drive
the engine, encode the selected outputs, and finalize a new recording session.
Preserve provenance, native source timing, and a defined equal-frame order.
Do not silently quantize events to render-block starts.

Instrument creation from recordings is also a separate recs editing workflow:
select or generate sample assets, assign slices and mappings, and persist a
self-contained instrument definition with sealed media references. Loops and
articulations remain playback instructions, not baked-in recording policy.

Do not subclass `SourceRecorder` or route engine output through `ChannelWriter`.
Their device capture, silence detection, and segmentation policies are not
instrument rendering semantics. Reuse document reading, finalization, encoding,
and shared DSP only where actually needed.

## Acceptance

| Boundary | Required evidence |
| --- | --- |
| Portable definitions | uFor codec/schema cases, rejected profiles, exact lifecycle/control traces, declared units and ordering |
| Common engine behavior | Fresh-instance isolation, exact event boundaries, routes, stops, snapshots, restoration, repeated releases, sustain crossings, chokes, and voice retirement |
| Synth audio | Established waveform convention, phase continuity/reset, pitch, envelopes, control modulation, layering, and output routing |
| Sample audio | Asset/slice bounds, shared decoded assets, traversal direction, loops, pitch, independent voice state, envelopes, and release tails |
| Partition invariance | Compare uninterrupted output with 64, 128, 256, and 1024-frame blocks and snapshot/resume; use explicit numerical tolerances |
| Host output | Correct output duration and frame placement, encoding, media integrity, provenance, and finalization; visible unsupported-profile errors |

Audio regressions write WAV at 48 kHz and last at least one second. Exact state
and action assertions are distinct from floating-point comparisons. Do not
promise bit identity between different numeric backends without supporting
evidence. Unsupported engine features must fail explicitly, not be ignored.

Live transport, audio-device latency, underruns, and VST hosting need separate
authorization and acceptance. Automated offline tests do not establish hardware
readiness; see [human verification](human.md).

## Additional work beyond the prompt

None.
