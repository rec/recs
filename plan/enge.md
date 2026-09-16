# enge

## Purpose

enge is the shared sound-engine project. Its two goals are:

1. consolidate tuney's synth implementation into one reusable synth engine; and
2. implement the corresponding sampler engine.

Both engines consume prepared uFor instrument actions and render bounded audio
buffers. They share exact output-frame scheduling, trigger and voice ownership,
release and retirement behavior, channel routing, phase/state handling, and
snapshot restoration. They must not become separate implementations with
slightly different lifecycle rules.

enge is engine-only, not synth-only. Its boundary excludes device I/O, MIDI and
OSC endpoints, GUI, transport deadlines, session/media discovery, file encoding,
and plugin-host integration. Those are host responsibilities. This does not
exclude sample decoding/preparation or waveform generation needed by the sampler
itself.

## Ownership

| Project | Responsibility |
| --- | --- |
| uFor | Portable scores, validation, instrument preparation, lifecycle traces, and language-neutral conformance cases |
| enge | Synth and sampler realization, engine preparation, voice state, bounded audio rendering, snapshots, and engine-level audio conformance |
| tuney | Authoring/UI behavior and application-specific keyboard/learning policy; its reusable synth implementation moves into enge |
| recs | Capture, asset inspection and session media, editing, offline-host integration, encoding, and export |
| Hosts and bindings | Performance-input adaptation, transport clocks, audio devices, MIDI/OSC, VST hosting, files, and delivery |

uFor determines what a score means. enge determines how the supported synth and
sample profiles turn its prepared actions into audio. A host decides when to run
enge and where audio goes.

## Current implementation

`~/code/enge/src/enge/synth.py` is the initial synth engine. It already:

- prepares a `SynthInstrumentScore` into its output sample rate and channel
  layout;
- renders `TraceAction` values in exact `(tick, ordinal)` order within
  nonempty half-open output-frame intervals;
- renders oscillator voices with explicit channel routes, resolved Hz pitch,
  held linear envelopes, minimum-hold release behavior, and optional
  transport-synchronized oscillator phase;
- snapshots and restores voice state so partitioned and resumed renders agree
  with one uninterrupted render; and
- shares tuney's established waveform start/length/period convention through
  `waveform_samples()`.

This narrow synth profile is an implemented first step, not a project limit.
Unsupported modulation, processing, curved envelopes, and richer generators
currently fail explicitly until their engine behavior is added with tests.

## Synth goal

Finish consolidating reusable synth behavior in enge. Keep one canonical
implementation of waveform shape, phase evolution, gain, envelope/release,
routes, state snapshots, and block partitioning. tuney should call or adapt this
engine rather than retaining an independently evolving waveform renderer.

Extend the synth profile deliberately, one declared uFor feature at a time.
Each extension needs exact state/action expectations and split-block/snapshot
tests before it becomes supported. Do not move tuney's UI, broader expression
authoring, or MIDI-host policy into enge.

## Sampler goal

Build the sampler alongside the synth engine, using the same uFor performance
and lifecycle contract. The sampler owns sample-engine preparation, decoded
asset reuse, traversal position, loops and direction, pitch ratio, per-voice
envelope and processing state, channel routing, release tails, and bounded
audio output.

uFor already prepares sample selection, trigger ownership, sustain and logical
release, choke, deterministic retirement, voice limits, linked takes, and
variation as portable traces. enge must consume those results rather than
reimplementing selection or pedal policy from raw events. Shared decoded assets
must be reused across voices; voice-local playback and DSP state must remain
independent.

The synth and sampler must produce the same required lifecycle behavior for
repeated and overlapping trigger IDs, releases, sustain transitions, chokes,
voice limits, stops, snapshots, equal-frame ordering, and arbitrary block
partitions.

## Next agent guidance

Work toward the two engine goals without widening into a host:

1. Define the common enge preparation/result API for prepared synth and sample
   instruments, bounded `advance()` calls, snapshots, restoration, and visible
   unsupported-profile diagnostics.
2. Complete synth consolidation by moving reusable tuney synthesis behavior
   behind that API and preserving the existing waveform convention in regression
   tests.
3. Add sampler preparation and traversal using uFor's prepared sample actions,
   then cover forward/backward/mirror direction, loops, pitch, stereo routing,
   release tails, and shared-asset memory behavior with 48 kHz WAV regressions.
4. Maintain common lifecycle and audio conformance across 64, 128, 256, and
   1024-frame partitions before considering a live host or VST wrapper.

Do not add audio-device code, MIDI/OSC connections, GUI, file output, or plugin
discovery to enge. Those integrations reuse the completed engines through host
adapters.

See [the offline instrument contract](sample-playback.md#offline-instrument-contract)
and [the uFor handover](ufor.md) for the portable contract enge realizes.

## Additional Work Beyond The Prompt

None.
