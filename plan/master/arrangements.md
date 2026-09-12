# Arrangements, sequences, and nested mixes

## Incomplete

General nested arrangements, typed ports, structured references, and the
cutover from Recs's audio-only edit schema remain unfinished. Existing edit
commands and rendering remain application behavior, not the completed portable
arrangement model described here.

## Sources and clips

A source references a recording stream, a sequence, an instrument-driven graph,
another arrangement's exported port, or a declared live endpoint. File assets
become source nodes through their typed reader. In-memory materialization is an
execution detail, not a portable source locator.

A clip names its source and lane, a source interval, a timeline start, and a
positive rational playback speed. Source positions use the source timebase;
timeline positions use the arrangement timebase. Resolve to physical time
before applying speed. For source interval `[a, b)`, start `s`, and speed `r`,
source time `u` appears at `s + (u-a)/r`, and duration is `(b-a)/r`.
Final sample-boundary conversion follows [Time](time.md).

The first profile uses speed 1. Audio speed changes require a selected resampling
or time-stretch operation, with its pitch behavior explicit. Musical clips can
follow a parent tempo map when marked beat-anchored. A physical recording stays
in physical time unless explicitly warped. Reversal is an operation, not a
negative speed quietly applied to requests and note lifecycles.

Illustrative placement of a recording stream:

```toml
[[sources]]
id = "interview"
dependency = "session"
port = "desk"

[[tracks]]
id = "speech"
stream_type = "stereo-audio"

[[clips]]
id = "answer"
source = "interview"
track = "speech"
source_start = 48000
source_end = 528000
timeline_start = 0
speed = { numerator = 1, denominator = 1 }
```

When both timebases are 48 kHz, this places ten seconds from the source at the
start of the arrangement. IDs and stream descriptors in this fragment would
be declared in the containing score.

## Mixing and automation

Routes connect explicit ports. Numeric audio summing, event merging, control
selection, and lighting blending are distinct operations. A track with
overlapping clips declares its overlap rule; unsupported combinations fail
validation. Stereo audio does not automatically become mono, and MIDI events
do not become sound without an instrument.

Clip gain is a linear audio multiplier. General effects are processor nodes.
A crossfade names both clips, its interval, and curve law; preserve the existing
equal-power behavior as a named audio mix contract. Existing independent
equal-power gain lanes use the squared-gain mapping in [Quantities](quantities.md).
Parameter automation uses the common structured target and curve rules.
Multiple control writers require
an explicit combiner, including manual overrides and automation.

Rendering declares a finite requested interval and a tail policy: truncate at
the end or retain a specified additional duration. Delays, release envelopes,
and reverberation may continue after the last clip. An open-ended live source
does not make an offline render silently infinite.

## A mix of mixes

An arrangement dependency exposes named output ports and optional exported
parameters. Its internals retain a private namespace. Every instance has its
own state, time mapping, and voice ownership. Definition-reference cycles are
invalid even when a contained DSP operation has internal feedback.

An outer clip can select a range from an inner arrangement. The compiler can
flatten or cache it only when it preserves state, pre-roll, tails, and parameter
scope. A cached render records definition/dependency digests and the realized
binding. A changed instrument or plugin binding invalidates that cached result.
Cache implementation is optional; correct nesting is not.

Keep authoring recipes separate from the resulting work. A recipe such as
“trim silence, calibrate, then mix” produces an arrangement and any derived
assets. Retain the recipe as provenance if useful, but playback does not need
to execute CLI strings to discover what the work means.

## Change from today

`recs/edit/schema.py` already defines `EditSpec`, `SourceSpec`, `TrackSpec`,
`BusSpec`, `ClipSpec`, `RouteSpec`, `AutomationSpec`, and `OutputSpec`.
Preserve its native integer-frame audio behavior, then replace audio-only
channels and string targets with typed ports and structured references.

`CompositionEdit` in `recs/edit/composition.py` is an implemented sequence of
editing commands, resolved recipes, and stages. It is not yet a general nested
arrangement. Compile those operations into canonical arrangement dependencies
and keep command history as provenance. `PartialEditSpec` can continue as an
internal authoring input during its replacement, but must not become a second
public playback format. Finalize each cutover by updating its consumers and
removing the replaced native schema.

`OutputSpec` currently combines a bus selection, range, encoding, normalization,
and path. Split public arrangement outputs from run output destinations. Retain
normalization as an explicit offline operation; whole-program normalization
cannot be promised for unknown future live audio.
