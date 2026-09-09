# Audio arrangement documents

Implemented initial profile of the [master format](../plan/master/master.md).
The native audio-edit document is now a Recs document with an arrangement body.
Old flat edit documents are no longer accepted. Session inputs use
`recording.toml`; successful renders finalize a new recording document beside
the generated media and operational journal.

```toml
format = "recs"
version = 2
kind = "arrangement"
id = "speech-edit"
name = "Speech edit"

[[timebases]]
id = "audio"

[timebases.rate]
numerator = 48000
denominator = 1

[body]
timebase = "audio"

[[body.tracks]]
id = "speech"

[body.tracks.stream]
timebase = "audio"
channels = ["channel-0"]

[[body.clips]]
id = "opening"
track = "speech"
source_start = 0
source_end = 48000
timeline_start = 0

[body.clips.source]
node = "take"
port = "audio"

[[body.nodes]]
id = "take"

[body.nodes.definition]
path = "take.recording.toml"

[[destinations]]
port = "main"
path = "audio/speech.wav"
format = "wav"

[[ports]]
id = "main"
direction = "output"

[ports.stream]
timebase = "audio"
channels = ["channel-0"]

[ports.binding]
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

Each node directly names a definition with `{ path, sha256? }`. Each clip selects
its public output with `{ node, port }`. Definitions resolve relative to the
containing document; public `ports` bind internal tracks, buses or child ports.
See the [composition design](composition-design.md) for connections and parameters.

Recording exports use stable stream IDs and optional zero-based consecutive
`channels`. Recs' CLI retains human-facing session selectors while authoring:
it writes a recording definition exposing the chosen stream/channel selection.
Raw audio files likewise receive recording metadata rather than a special source
variant. The resolver follows recording continuations, verifies selected assets,
and retains native gaps and offsets. Open recordings and unresolved historical
placement are rejected. Nested arrangement outputs retain their native frame
coordinates. Unsupported instrument realization fails during preparation.

Automation targets are structured tables, such as
`{ kind = "clip", node = "opening", parameter = "gain" }`. A route target also
names `destination`. Gain remains a linear amplitude multiplier. Existing
equal-power gain interpolation retains its squared-gain formula and its base
value before the first knot.

The Pydantic definition is `ufor.arrangement.ArrangementDocument`; its
`model_json_schema()` describes this implemented profile. The parser and TOML
writer are in `recs/edit/schema.py`. Authoring recipes still describe operations
and defaults; generated arrangements use the new native document. Resolved
composition stages retain their recipe provenance and store the new documents.

## Validation ownership

Ufor validates identifier uniqueness, clip and routing references, matching route
channel layouts and timebases, acyclic bus routing, automation targets, output
references, and destination ports. Frame positions require integers and gains
must be finite. `Arrangement.bus_order` supplies dependency order to consumers.

Applications still inspect media to check source channel counts and available
frames, determine rendered extents, and validate output encodings. Arrangement
`ParameterTarget` specializes the shared modulation `Target` address while
retaining its existing clip, bus and route selectors and gain-only profile.
