# Time, clocks, and transport

## Incomplete

Portable scheduling, checkpoint restoration, real-time lateness policies, and
cross-machine clock synchronization remain execution work. Capture timebases,
clock observations, and native event timing are the completed foundation.

## Completed

Part of the [master proposal](master.md). These rules apply to every timed
payload; domain documents must not invent their own meaning for a timestamp.

## Exact positions

Store integer ticks in a named timebase. A physical timebase declares a positive
rational rate `{numerator, denominator}` in ticks per second. Audio at 48 kHz
uses 48,000/1; a 44.1 kHz asset keeps 44,100/1. A device clock and a timeline
timebase are distinct: the first is a measured oscillator, the second is a
coordinate system.

A position is `{timebase = "audio", tick = 48000}`. A duration has the same
shape but is an interval, not an absolute position. Within a stream or clip
that declares its timebase, its integer positions inherit that timebase.
Positions are signed to permit pre-roll; payload array offsets remain
nonnegative. All stored ranges are half-open `[start, end)`.

For rate `n/d`, tick `k` represents exactly `k*d/n` seconds from its origin.
Do rational arithmetic between timebases. Convert an event to a destination
sample frame once, using nearest integer with ties to even. Keep its original
position in the source document; never round each elapsed delta independently.
For example, tick 44,100 at 44.1 kHz maps exactly to frame 48,000 at 48 kHz.
Two seconds of output always span exactly 96,000 output frames.

Sampled streams at different rates require a declared resampler. Changing a
timestamp does not resample an array. A host uses one scheduling timeline and
explicit converters at rate boundaries, rather than imposing 48 kHz on every
kind of data.

## Musical time

A musical timebase declares integer ticks per quarter note and a tempo map.
Start with piecewise constant tempo segments whose positive quarter-note
duration is a rational number of seconds. Store time signatures separately for
bar/beat display. Tempo ramps can follow when their integration rule is specified.

```toml
[[timebases]]
id = "beats"
kind = "musical"
ticks_per_quarter = 960

[[timebases.tempo]]
tick = 0
seconds_per_quarter = { numerator = 1, denominator = 2 }

[[timebases.tempo]]
tick = 7680
seconds_per_quarter = { numerator = 2, denominator = 3 }
```

The first eight quarters last four seconds; the next quarter ends at 14/3
seconds. Tempo applies from the segment's tick onward. A map begins at or
before the earliest musical position it resolves. Edits preserve beat positions
when changing tempo; physically timed recordings do not stretch implicitly.
Freeze a selected tempo map in the run record.

## Capture clocks and synchronization

Each capture stream names a clock. Clock observations contain source tick,
session tick, timing source, and uncertainty. Multiple observations describe
piecewise affine mappings to the session timeline, including measured drift.
Clock discontinuities start new segments; never fit a single mapping across a
reset. Preserve native counts even when a host estimates a better alignment.

Arrival time, source-provided time, and scheduled execution time are separate
fields when available. A host-monotonic arrival stamp is useful evidence but
does not prove when the remote device produced the data. Record the capture
origin for process-local clocks so stored monotonic values remain interpretable.

Absolute UTC anchors connect a timeline position to a date for broadcasts and
logs. Wall-clock corrections must not make running playback jump. Resolve a
scheduled UTC start to the host's monotonic clock, record the decision, and
report subsequent clock error. Cross-machine synchronization needs measured
offset and drift; a shared format alone cannot synchronize devices.

OSC bundles carry execution timetags, but OSC does not provide clock
synchronization. Preserve bundle time independently of reception time.
[OSC 1.0 specification](https://opensoundcontrol.stanford.edu/spec-1_0.html).

## Scheduling and state

Events carry an integer ordinal unique within their stream. Sort by resolved
time and then ordinal. Merging streams uses the connection's declared input
order before each stream's ordinal for ties. Do not silently reorder note-off
and note-on messages because their timestamps coincide.

Playback owns position, start/stop/pause, loop boundaries, and initial state.
Before seeking, stop voices owned by the previous transport position, restore
state from a declared checkpoint or replay from the beginning, and suppress
external actions during reconstruction. Stateful DSP needs pre-roll or a
checkpoint; it cannot generally start at an arbitrary clip boundary unchanged.

Real-time sinks declare acceptable lateness and an explicit action for late
data. Events that end a note need different handling from a stale pixel frame.
Queues are bounded; a discarded quantity or event produces a run observation.
Offline rendering has no lateness and uses the same ordering and state rules.
Processor latency, analysis lookahead, and output latency are accounted for
separately; alignment cannot give a live process advance knowledge of input.

## Change from today

`EditSpec.sample_rate` and its frame positions already provide exact audio
timing. Preserve those counts while moving the rate into a named timebase.
Recsam events currently inherit an output-frame clock; give them a sequence
timebase. MIDI capture in `recs/midi/writer.py` currently quantizes deltas into
SMF ticks. Record native timing first and make SMF a deliberate export.
Tuney's `CharPress.time` is in milliseconds; convert it explicitly rather than
reinterpreting that number as sample frames.
