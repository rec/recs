# Sample Playback

## Status And Scope

This is an implementation proposal, not an implemented sampler or approval to
implement every candidate feature. It places sample-bank creation and playback
within the current Recs architecture.

Related documents:

- [Sample Bank Format](../doc/sample-format.md): proposed TOML representation.
- [Sample Format Additions](sample-format.md): candidate features awaiting review.
- [Editing Tools](editing-tools.md): planned session-to-session editing framework.

Recs already has recording, MIDI capture, audio-file I/O, and session records.
The `recs/edit/` framework is still a plan. Sample playback needs a new stateful
audio engine; it is not simply another recording source or a collection of
independent edit commands.

Microtonality remains covered by its separate specification. This task creates
only this document, not code, dependencies, or changes to the recording daemon.

## Separate Creation From Playback

### Bank Creation

An audio edit creates a playable instrument definition:

1. Read selected recordings from an input session record.
2. Extract sample material or define slices, assign note and velocity ranges,
   and attach playback settings and tags.
3. Write a new session directory containing generated audio,
   `sample-bank.toml`, the session record, and the resolved edit definition
   required by the editing plan.

Bank references point to audio inside the new directory. Slices may share one
generated audio file rather than duplicate it. The resulting bank does not
require the original recording session for playback.

Loops, articulations, and controller behavior remain instructions for the
player. They are not permanently baked into the sample files. Unsupported
input media is omitted according to the editing plan's media-selection rules.

### Bank Playback

A player combines a bank with timed performance events to produce audio.
Start with offline rendering of recorded MIDI. Live playback can subsequently
host the same engine without changing bank semantics.

## Proposed Sampler Subsystem

Introduce `recs/sampler/`, separate from the recording machinery. The following
are proposed class boundaries, not existing classes:

| Class | Responsibility |
| --- | --- |
| `SampleBank`, `SampleSlot` | Pydantic models matching the TOML specification |
| `PreparedBank` | Validated assets, resolved settings, and efficient note/velocity lookup |
| `PerformanceState` | Controllers, pedals, articulation selection, alternate-take counters, and random state |
| `Voice` | Playback position, direction, loop state, envelope, and filter state |
| `Sampler` | Consume timed events, manage voices, and render audio blocks |

Separate immutable bank definitions from mutable performance and voice state.
Resolve TOML, validation, and inherited settings before rendering rather than
repeating that work inside the audio loop.

Use composition, not a subclass for every feature. The candidate features fall
into four areas:

- Slot selection: layers, alternate takes, and articulations.
- Voice lifecycle: release samples, pedals, choke groups, and polyphony.
- Audio processing: direction, loops, envelopes, EQ, modulation, and crossfades.
- Organization: groups, named slices, microphone links, and routing.

Only implement retained features after their defaults and interactions are
specified. For example, selection, choking, and layering cannot independently
make conflicting decisions about voices created by the same event.

## One Engine, Two Hosts

The core consumes events at integer output-frame positions and renders bounded
audio blocks. It has no dependency on audio devices, session-record writing, or
the file-output policy. Asset loading is handled outside its rendering loop.

### Offline Host First

The offline host reads recorded MIDI and the bank, schedules events, drives the
engine, and writes the resulting audio as a new Recs output session.

Convert MIDI timing, including tempo changes, into output-frame positions
before scheduling. Split render blocks at event boundaries so notes and
controller changes are not quantized to the beginning of a block. Preserve a
defined order for events at the same frame.

The host owns session creation, output encoding, provenance, and file lifecycle
entries. The sampler only supplies audio. Offline rendering provides a
deterministic environment for establishing behavior and regression tests before
taking on live latency.

### Live Host Later

The live host timestamps incoming MIDI, schedules it against the output audio
clock, and drives the same sampler through an audio output stream.

Do not put file access, decoding, blocking operations, or configuration parsing
in the audio callback. Prepare assets and buffers outside that callback. See
the [Sounddevice callback requirements](https://python-sounddevice.readthedocs.io/en/latest/api/streams.html).

Live playback is a separate host, not a reason to couple the sampler to the
recording daemon. Device latency, event scheduling, and underrun behavior need
their own validation after offline correctness is established.

## Reuse Existing Recs Components

Reuse the existing Pydantic/TOML conventions, Pydantic/Tyro command models,
`reccy.logging`, and session-record reader/writer. Use the existing audio
dependencies where suitable: `soundfile` provides block-based file I/O and
NumPy audio arrays. See [SoundFile documentation](https://python-soundfile.readthedocs.io/en/0.13.1/).

Do not subclass `SourceRecorder` or route rendered output through
`ChannelWriter`. Those classes carry device-recording, silence-detection, and
segmentation policies that do not belong in sample playback. An offline render
must preserve its requested timeline rather than inherit recording decisions
about quiet material.

The planned editor and sampler should share DSP primitives when both actually
need them. Do not build a general-purpose processing framework in advance or
force unrelated recording classes to serve as sampler abstractions.

## DSP Backend And Resource Use

The current dependencies are not a complete sampler engine. Before writing
resampling and other expensive DSP ourselves, evaluate a proven playback engine
such as [sfizz](https://sfz.tools/sfizz/) against the retained TOML semantics.

Check direction and loop behavior, modulation composition, event timing,
channel layouts, and deterministic selection. A backend that silently changes
those semantics is not a conforming implementation. Translating the format to
another engine's input syntax is an option to evaluate, not an assumption that
all features map faithfully.

If no complete engine fits, reuse suitable DSP libraries for the expensive
primitives while keeping Recs' selection and lifecycle rules explicit. Backend
and dependency choices require evaluation before implementation; this proposal
does not select or add a dependency.

Share decoded sample data between voices. Each voice owns its playback and DSP
state, not a private copy of the sample. Bound rendering buffers and define a
cache budget for large banks. Do not assume that loading every recording into
memory is acceptable.

Avoid Python loops over individual samples for expensive DSP. Measure CPU,
memory, and latency using realistic polyphony and multichannel material before
claiming live suitability.

## Suggested Implementation Order

1. Review and trim the candidate feature list, then resolve the retained format
   semantics and cross-feature interactions.
2. Implement bank parsing, validation, asset resolution, and bank creation in
   coordination with the editing framework.
3. Evaluate the DSP backend and establish the event-driven block-rendering API.
4. Implement deterministic offline MIDI rendering for the base format, producing
   a new session record and generated audio.
5. Add retained features incrementally, with focused behavior and audio
   regression tests for each addition and its interactions.
6. Verify that event timing and deterministic selection are independent of
   render block size. Check voice limits and shared-asset memory behavior.
7. Add live MIDI and audio hosting only after offline rendering is correct, then
   measure latency, resource use, and underruns on target hardware.

Follow Recs' existing 48 kHz, at-least-one-second WAV convention for digital
audio regression fixtures. Test rendered output and visible behavior rather
than private implementation details. Hardware checks remain distinct from
automated offline verification.

## Additional Work Beyond The Prompt

None.
