# Radio programmes, live sections, and rebroadcast

Part of the [master proposal](master.md). A broadcast document schedules content
that may not exist yet. It describes intended playout; a run records actual
playout. A completed recording and a future programme are different objects.

## Programme structure

A broadcast exposes programme output ports and contains ordered sections. Each
section names a source, scheduled start, duration policy, transition, and
behavior when content is unavailable. A source may be a recording, a nested
arrangement, a live input, or a live relay from another programme.

Every section uses exactly one start rule:

- `at`: a fixed position on the programme timeline, optionally anchored to UTC.
- `after`: begin after the named previous section actually finishes.
- `cue`: begin on an operator cue, with an earliest position and deadline.

Every section uses exactly one end rule: a fixed duration, a fixed end position,
or a cue/source-end bounded by a maximum duration. Reject cyclic `after`
dependencies. Unresolved cue timings make the plan provisional, not malformed.

Illustrative section within a one-hour programme whose `programme` timebase has
one tick per second:

```toml
[[sections]]
id = "guest"
source = "guest-feed"
start = { kind = "at", tick = 600 }
end = { kind = "at", tick = 900 }
transition = { kind = "cut" }
unavailable = { kind = "replacement", source = "standby-bed" }
late_join = "current"
capture = true
```

This reserves minutes 10 through 15. If the feed appears at 10:20, a `current`
late join takes its then-current content and still ends at minute 15. It does
not replay the missing 20 seconds. A replacement source must be prepared for
the entire reserved interval and declare its looping or end behavior.

## Three uses of live material

| Intent | Definition |
| --- | --- |
| Future live section | Logical microphone or contributor endpoint to be bound for this run |
| Live relay | Another programme's currently produced stream, with latency/buffer policy |
| Later replay of a live section | Sealed capture asset and its actual timeline placement |

A delayed relay additionally declares a required buffer duration. It can start
only when that amount of captured data exists. A source that has not happened
yet cannot be rendered ahead of time. Offline preparation may render the known
sections and show unresolved intervals, but must label that result incomplete.

The programme can be rebroadcast in two intentional ways. Replaying the captured
programme reproduces what aired. Running its definition again repeats recorded
sections and obtains new live material for its live sections. Selecting between
these creates a concrete replay arrangement or a new run; the player must not
silently choose according to whether a microphone happens to be connected.

## Transitions, overruns, and failures

An overlap requires an explicit crossfade or mix rule. At a hard start/end, apply
the declared cut/fade rule to the preceding source even if it overruns. A
follow-on section shifts with its predecessor. A cue-based section reaching its
deadline takes the authored action: use replacement, skip to a named section,
or stop the programme. These policies are visible editorial choices.

Availability distinguishes absent connection, insufficient buffered content,
decode failure, and valid silence. Silence alone does not prove a feed is dead.
Set a freshness criterion in the source binding, such as input progress, rather
than guessing availability from amplitude.

Record every actual start/end, switch, source instance, dropout, replacement,
operator cue, and output-delivery result. Capture the programme bus and, when
requested, the constituent live sources. An as-aired arrangement references
these captures and actual decisions so later rebroadcast never depends on
recreating an operator's choices from memory.

A failed delivery is not proof that nothing aired. Record source production,
local output submission, and remote delivery observations separately to the
extent the adapter can observe them.

## Application boundaries and change from today

Recs resolves and renders content, journals decisions, and records programme
audio. Streamo delivers a selected programme port and supplies supported live
feed adapters. Showco presents run readiness, timing, actionable failures, and
operator cues. Lyte can consume synchronized programme controls through another
output port. Scheduling is owned by one broadcast transport; applications must
not maintain competing copies of section position.

`streamo/config.py:Streamo` currently selects an audio device/channel and service
configuration, alongside video/image settings. Add programme audio as an
explicit input binding in the eventual cutover. `streamo/programs.py` currently
parses bitrate output; its filename does not imply an existing radio rundown
model. Service credentials and Streamo's video features remain deployment
configuration outside the common content format.

Showco's `ActionResult`, action log, and service status remain runtime views.
They can report broadcast run observations without becoming the authoritative
programme definition. The planned/live/as-aired distinction is new functionality.
