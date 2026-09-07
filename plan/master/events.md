# Events, requests, and sequences

Part of the [master proposal](master.md). Events say that something happened at
a time; they do not imply a continuously sampled value between occurrences.

## Event envelope

Each stream declares its timebase and permitted event schema. Each event has
`tick`, `ordinal`, `kind`, and a typed payload. The ordinal breaks timestamp
ties and also identifies the event within its stream. Source identity and
capture-clock observations belong to its recording context. Authored sequences
use the same records as captured semantic event streams.

| Event family | Payload and identity |
| --- | --- |
| Performance | Trigger, release, and scoped control change; part and trigger ID |
| Key | Physical key identifier, logical text when available, press/release, modifiers, repeat flag |
| Parameter change | Structured destination, typed value, and scope |
| Cue | Named timeline marker or transport cue, with a declared action |
| Request | Named endpoint operation, typed arguments, request ID, and replay policy |
| Result | Request ID, observed completion time, outcome, and typed result or error |
| Raw protocol | Protocol identifier, exact payload bytes, direction, and transport metadata |

Trigger IDs identify an active performance instance, not a pitch. Two overlapping
notes on the same key must have distinct IDs and independently match releases.
Retain recsam's `part`, `trigger_id`, normalized velocity, and optional
`pitch_hz`. A zero-velocity semantic trigger remains a trigger. MIDI's
interpretation of particular wire messages belongs to its adapter.

Illustrative inline sequence body:

```toml
timebase = "audio"
event_schema = "recs.performance"

[[events]]
tick = 0
ordinal = 0
kind = "trigger"
part = "lead"
trigger_id = "note-1"
key = 69
velocity = 0.8
pitch_hz = 440.0

[[events]]
tick = 48000
ordinal = 1
kind = "release"
part = "lead"
trigger_id = "note-1"
```

At 48 kHz these events hold a note for one second; its audible release tail
depends on the instrument. A sequence declares its extent separately from the
last event so trailing silence or held control state is representable.

## Raw capture and semantic editing

Preserve raw MIDI or OSC when fidelity to an unknown device matters. A semantic
projection is a separate derived stream with a recorded mapping and source
event references. Raw and semantic streams are related representations, not two
sets of commands to dispatch simultaneously.

MIDI adapters own channel/part mapping, overlapping-note matching, controller
resolution, sustain interpretation, and conversion to pitched performance.
Keep SysEx or other unrecognized messages as typed raw data. Export to a more
limited protocol reports quantization and unsupported per-note expression.

OSC capture keeps address, type tags, arguments, bundle membership, raw bytes,
and source timetag where present. An address alone does not tell us whether a
message is state, a trigger, or a request with side effects. Its endpoint profile
supplies that interpretation. Bundles and typed arguments come from the
[OSC specification](https://opensoundcontrol.stanford.edu/spec-1_0.html).

Keys need both physical identity and optional resulting text: the same physical
key can produce different text under another layout. Replaying a captured key
sequence into an instrument uses an explicit key mapping. Sending it to the
operating system is a separate endpoint action, never an effect of opening it.

## Requests and effects

A request schema names an operation such as `set_parameter`, `start_recording`,
or `take_live_source`, with concrete argument types. Do not put arbitrary shell
commands, HTTP templates, or Python expressions into universal event bodies.
An installed adapter implements the operation and owns transport details.

The operation declares whether it is state-setting, repeatable, or a one-time
action. Capturing a request does not authorize its later execution. Offline
rendering and seek reconstruction simulate requests or retain them as events;
only a run explicitly binding an enabled action endpoint can dispatch them.
Recording a request's result does not guarantee the same result on replay.

## Editing, loops, and seeking

A sequence clip selects a half-open event interval and translates its timestamps
using [Arrangements](arrangements.md). Include parameter state at its start
through a checkpoint or replay. Start-inside-note behavior is explicit:
`retrigger_active` creates a new scoped trigger at the clip boundary;
`omit_active` waits for subsequent triggers. The former restarts envelopes and
does not reproduce the sound of a sustained voice already in progress.

At a clip end, release all triggers owned by that clip and let the arrangement's
tail policy determine retained output. At a loop boundary, close that iteration's
trigger ownership and reconstruct the next iteration's starting state. Namespace
trigger IDs by clip instance and loop iteration to prevent collisions. Requests
with effects are not repeated by a loop unless its execution policy allows it.

## Change from today

Move the shared event envelope and performance types out of
`recs/recsam/events.py` when adopting the model, and update every consumer.
Do not create a second sampler-specific performance hierarchy. Preserve useful
MIDI and OSC capture data while replacing their unrelated timing conventions.
Tuney's `CharPress` maps to key events; its private cached character and callback
handles remain runtime details. Recs session operational events become typed
run observations rather than being presumed playable content.
