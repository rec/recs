# Remaining Standard SFZ Import Work

## Current Baseline

`recs.recsam.sfz.read()` already returns `SfzReadResult`, containing a validated
recsam instrument when one can be constructed and an ordered collection of
unimplemented features with source locations. The completed correctness work
includes velocity response, asset-aware loop and channel defaults, envelope
shape mapping, release-trigger distinctions, half-open loop endpoints, and
basic inheritance.

The remaining goal is a lossless, well-diagnosed import of useful,
non-vendor-specific SFZ 1 and SFZ 2 behavior. Unsupported behavior must remain
visible; it must never be silently approximated.

Vendor extensions remain outside the compatibility promise. A general recsam
concept should be added only when it is useful independently of SFZ.

## 1. Opcode Registry And Diagnostics

Create one registry classifying every standard header and opcode as:

- supported;
- dependent on asset metadata;
- dependent on a new recsam model;
- dependent on an external controller binding;
- deferred because player semantics are ambiguous; or
- a vendor extension.

Use that registry to generate diagnostics and a public support table so code
and documentation cannot drift. Preserve the current file, line, header,
opcode, value, and reason for every unimplemented feature.

Add SFZ 2 `#define` expansion at token values. Reject recursive and undefined
variables, preserve original source locations, and do not add general textual
evaluation. Register `<curve>`, `<effect>`, and `<sample>` even while their
semantics remain unsupported.

## 2. Currently Representable Features

Implement exact mappings that fit the existing recsam model:

- key and velocity layer crossfades, including only curve shapes with an exact
  counterpart;
- ordered alternatives after defining when their counter advances;
- random alternatives only after the reproducibility design in
  [Remaining Recsam Format Work](sample-format.md);
- key-dependent amplitude, general pitch-key tracking, velocity-to-pitch, and
  key- or velocity-dependent envelope times;
- remaining transport-independent aliases and documented SFZ defaults for
  start, end, loops, gain, tuning, transposition, direction, triggers, and
  exclusive groups.

Keep discrete eligibility ranges separate from crossfade ranges. Reject region
sets whose layering or alternative-selection scope cannot be represented
coherently.

## 3. New General Recsam Concepts

Design these independently before adding importer mappings:

- loop direction and finite loop counts;
- voice limits, voice stealing, repeated-trigger masking, and release-tail
  termination;
- delayed start, repeat count, end fade, stereo width, channel position,
  channel swapping, and polarity inversion;
- missing modulation-envelope and LFO behavior such as LFO fade-in;
- exact conversion between SFZ equalizer bandwidth and recsam resonance, if the
  transfer functions can be specified and tested.

Do not add SFZ opcode names to recsam. Filters remain blocked on a separate
filter design.

## 4. Controller Bindings

Design a companion binding document that maps MIDI and other protocols onto
recsam's transport-neutral events and named controls. An SFZ import containing
bindings will need to return both an instrument and bindings.

Only then consider MIDI channel ranges, CC conditions and modulation, pitch
bend, aftertouch, key switches, previous-key conditions, initial CC values, and
controller curves. Until that format exists, report these as requiring a
controller binding.

## Explicit Deferrals

- filters, filter envelopes, and filter LFOs;
- beat synchronization without a transport and tempo model;
- output buses, sends, and `<effect>` without a routing graph;
- generated waveforms and waveguides without a synthesis-source model;
- random delay, offset, pitch, and gain without reproducible random state;
- MD5 assertions unless Recs adopts general asset verification;
- vendor extensions, including `#include`.

## Tests

Use compact handwritten SFZ fixtures and regression snapshots. Cover every
supported opcode's defaults, bounds, and units; inheritance order; mono and
stereo assets; embedded loops; diagnostics for all standard unsupported
opcodes; `#define`; crossfades; coherent alternatives; and exact source
locations after preprocessing.

Audio fixtures must remain WAV files at 48,000 samples per second and at least
one second long. Ambiguous reference behavior is a documented deferral, not a
fixture copied from one player's interpretation.

## Completion Criteria

- Every standard SFZ 1 and SFZ 2 construct has one registry classification.
- Every successful conversion preserves all represented behavior.
- Every unsupported construct has a precise location and explanation.
- The generated support table comes from the runtime registry.
- Recsam additions remain protocol-neutral and independently useful.
- The full suite does not access real MIDI devices.

## Additional Work Beyond The Prompt

None.
