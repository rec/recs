# Audio arrangement scores

Implemented initial profile of the [master format](../plan/master/verification-procedures.md#recs-a-common-language-for-things-that-happen-in-time).
The native audio-edit score is now a recs score with an arrangement body.
Old flat edit scores are no longer accepted. Session inputs use
`recording.toml`; successful renders finalize a new recording score beside
the generated media and operational journal.

```toml
format = "recs"
version = 3
kind = "arrangement"
name = "speech-edit"
title = "Speech edit"
inputs = []

[[timebases]]
name = "audio"

[timebases.rate]
numerator = 48000
denominator = 1

[body]
timebase = "audio"

[[body.tracks]]
name = "speech"

[body.tracks.stream]
timebase = "audio"
channels = ["channel-0"]

[[body.clips]]
name = "opening"
track = "speech"
source_start = 0
source_end = 48000
timeline_start = 0

[body.clips.source]
part = "take"
output = "audio"

[[body.parts]]
name = "take"

[body.parts.score]
path = "take.recording.toml"

[[destinations]]
output = "main"
path = "audio/speech.wav"
format = "wav"

[[outputs]]
name = "main"

[outputs.stream]
timebase = "audio"
channels = ["channel-0"]

[outputs.binding]
track = "speech"
```

The first audio profile has one physical timebase with an integer sample rate.
Tracks and buses expose a sampled audio type, full-scale amplitude units, and
ordered channel names. File paths and encodings live in `destinations`, outside
the arrangement body. A render requires exactly one destination per exported
output; an intermediate arrangement can have none.
Clip ranges remain native half-open sample-frame intervals. Mismatched source
rates require explicit conversion and are currently rejected by preparation.
The pure `convert_tick` operation converts exact positions and never resamples
audio. Musical time and generalized DSP remain later capabilities.

Each part either names a definition with `{ path, sha256? }` or contains a
complete inline score. Each clip selects its public output with `{ part, output }`.
Definitions resolve relative to the containing score; public `inputs`, `outputs`
bind internal tracks, buses or child outputs. See the [composition
design](../../ufor/doc/composition-design.md) for connections and parameters.

Recording exports use stable stream IDs and optional zero-based consecutive
`channels`. recs' CLI retains human-facing session selectors while authoring:
it writes a recording definition exposing the chosen stream/channel selection.
Raw audio files likewise receive recording metadata rather than a special source
variant. The resolver follows recording continuations, verifies selected assets,
and retains native gaps and offsets. Open recordings and unresolved historical
placement are rejected. Nested arrangement outputs retain their native frame
coordinates. Unsupported instrument realization fails during preparation.

Generated automation is an inline `AutomationScore` part with a public `control`
output. A `body.control_clips` entry places its source interval on the audio
timeline. The initial recs renderer accepts only an automation timebase that
exactly matches the arrangement's audio rate. An `ArrangementGainTarget` names a
clip, bus, or route, and route targets also name `destination`. Gain remains a
linear amplitude multiplier. Equal-power gain interpolation retains its
squared-gain formula and the declared route, bus, or clip gain before its first
knot.

The Pydantic definition is `ufor.arrangement.ArrangementScore`; its
`model_json_schema()` describes this implemented profile. The parser and TOML
writer are in `recs/edit/schema.py`. Authoring recipes still describe operations
and defaults; generated arrangements use the new native score. Resolved
composition stages retain their recipe provenance and store the new scores.

## Validation ownership

uFor validates identifier uniqueness, clip and routing references, matching route
channel layouts and timebases, acyclic bus routing, control-clip references,
output references, and destination ports. Frame positions require integers and
gains must be finite. `Arrangement.bus_order` supplies dependency order to
consumers.

Applications still inspect media to check source channel counts and available
frames, determine rendered extents, and validate output encodings. Arrangement
`ArrangementGainTarget` retains the arrangement's clip, bus, and route selectors
and gain-only profile.
