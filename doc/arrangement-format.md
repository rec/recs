# Audio arrangement documents

Implemented initial profile of the [master format](../plan/master/master.md).
The native audio-edit document is now a Recs document with an arrangement body.
Old flat edit documents are no longer accepted. Session inputs use
`recording.toml`; successful renders finalize a new recording document beside
the generated media and operational journal.

```toml
format = "recs"
version = 1
kind = "arrangement"
id = "speech-edit"
name = "Speech edit"
timebases = [{ id = "audio", rate = { numerator = 48000, denominator = 1 } }]

[body]
timebase = "audio"

[[body.sources]]
id = "take"
file = "take.wav"
channels = [0]

[[body.tracks]]
id = "speech"
stream = { timebase = "audio", channels = ["channel-0"] }

[[body.clips]]
id = "opening"
source = "take"
track = "speech"
source_start = 0
source_end = 48000
timeline_start = 0

[[body.outputs]]
id = "main"
source = "speech"

[[destinations]]
port = "main"
path = "audio/speech.wav"
format = "wav"
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

Source channel indices are zero-based. A session source uses
`record = "session/recording.toml"` plus
`selector = { source = "device", track = "voice", channel = 0 }`; omit the
selector's channel to select the complete track. Source and track names may
contain colons without becoming ambiguous. CLI channel selectors retain their
existing human-facing numbering and are resolved before saving the document.
The resolver follows recording continuations, verifies selected asset hashes,
and retains native gaps and offsets within files. Open recordings and selected
streams with unresolved historical placement are rejected.

Automation targets are structured tables, such as
`{ kind = "clip", node = "opening", parameter = "gain" }`. A route target also
names `destination`. Gain remains a linear amplitude multiplier. Existing
equal-power gain interpolation retains its squared-gain formula and its base
value before the first knot.

The Pydantic definition is `recs.model.arrangement.ArrangementDocument`; its
`model_json_schema()` describes this implemented profile. The parser and TOML
writer are in `recs/edit/schema.py`. Authoring recipes still describe operations
and defaults; generated arrangements use the new native document. Resolved
composition stages retain their recipe provenance and store the new documents.
