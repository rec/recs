# MIDI Rediscovery

## Scope

Make configured MIDI inputs resilient to ordinary USB device lifecycle changes:

1. Recs starts while no selected MIDI input exists.
2. A matching MIDI port appears later and begins recording without restarting
   Recs or the recording session.
3. That port disappears.
4. It appears again and resumes recording into a new MIDI file.

Initial absence is a normal `waiting` state. It must not create a Recs warning,
an error record, or an operator-facing failure.

This is generic MIDI input handling. It does not add a Flow 8 profile, MIDI
output, device control, routing, or message transformation.

## Current State

`MidiRecorder.start()` opens the selected input ports, and the current
rediscovery attempt calls input enumeration from every `poll()`. A read failure
finishes the current writer and removes the port, so a later poll can reopen it.

This is incomplete:

- mido input enumeration can be expensive or block, so it must not run on every
  recorder loop iteration;
- a port that vanishes without a read error has no defined transition;
- configured prefixes are reported as ad hoc rows, which cannot distinguish a
  waiting selector from a previously connected port;
- an unavailable MIDI backend can produce the same warning on every discovery
  attempt;
- reconnect files need a stable, explicit lifecycle and unique paths.

## Configuration And Identity

Continue to use `Cfg.midi.midi_include` and `midi_exclude` as the selection
interface. They are prefix selectors, so the recorder must retain both:

- the configured selector, such as `"FLOW 8"`;
- the concrete mido port name selected at a particular time.

Do not introduce a MIDI-only device configuration type. The existing selector
configuration is sufficient. A higher-level declared hardware specification may
refer to these selectors, but it must not replace Recs' matching rules.

## Lifecycle

Add a small discovery state machine to `MidiRecorder`, owned entirely by the
recorder thread:

- `waiting`: a configured selector has no matching open port.
- `recording`: a concrete port is open and its writer accepts messages.
- `failed`: opening, reading, or closing a concrete port failed. The error is
  recorded once for that failure transition; the selector remains eligible for
  later discovery.

Use a monotonic `MIDI_DISCOVERY_INTERVAL_SECONDS` deadline. The main recorder
loop calls `MidiRecorder.poll()` frequently, but `poll()` enumerates mido ports
only when discovery is due. A discovery failure records one warning and delays
the next attempt by the same interval.

At every discovery:

1. Enumerate mido input names and apply existing include/exclude selection.
2. Mark configured selectors without a matching concrete port as `waiting`.
3. For a newly matching concrete name, open the port and create a writer.
4. For an open port no longer returned by enumeration, close it, finish its
   current file, emit a `midi_source_stopped` record event with reason
   `disconnected`, and move its selector to `waiting`.
5. Do not reopen a port in the same discovery pass after an open failure. It is
   retried at the next interval.

During normal message polling, a read failure follows the same close-and-finish
path, emits `midi_source_failed`, and waits until a later discovery. The next
successful appearance creates a new writer and `midi_source_started` event.

## Files And Record

Each connected period writes a separate standard MIDI file. Its name includes
the concrete port and the local start timestamp, using the same compact
timestamp style as audio filenames. Choose a numeric suffix only when a file
with that port and start timestamp already exists:

```text
midi/FLOW 8-20260823-163829.mid
midi/FLOW 8-20260823-163829-2.mid
```

Every writer is finished exactly once, whether through normal shutdown,
disconnect detection, or read failure. Its `file_finished` record entry is
written before the corresponding stopped or failed source event. Do not retain
an in-memory writer after it has been finished.

Existing `midi_source_started`, `midi_source_failed`, and `file_finished`
records remain valid. Add `midi_source_stopped` only for a clean disappearance;
use `midi_source_failed` for a port or writer error.

## Status And Errors

`status_snapshot().midi` should publish one row per configured selector and
each distinct active concrete port, with:

- selector and concrete port name where available;
- lifecycle state;
- current-period message count and last-message timestamp;
- last failure message and time, if any.

Show `waiting` for absent selected devices. It is not an error. A concrete
`failed` state remains visible until that device reconnects, but it must not
block audio recording or other MIDI inputs.

## Tests

1. Start with no matching ports and assert a `waiting` status row with no
   warnings or record errors.
2. Advance a fake monotonic clock, add a matching port, and assert it opens and
   records a message without restarting the recorder.
3. Remove that port from discovery while its reads still succeed; assert the
   writer closes, a stopped event is recorded, and status returns to `waiting`.
4. Re-add the port and assert a second file with a numeric suffix, new started
   event, and fresh message counters.
5. Make `iter_pending()` fail and verify exactly one failure event and finished
   file before the next discovery attempt.
6. Verify a missing mido backend produces one rate-limited warning per failed
   discovery interval, not one per main-loop iteration.
7. Verify two selected ports can independently wait, connect, fail, and
   reconnect.
8. Run a manual USB test: start Recs with no controller, attach one, remove it,
   reattach it, and inspect status plus both MIDI files and record events.

## Implementation Order

1. Add explicit selector and concrete-port runtime state plus a fake monotonic
   clock to MIDI recorder tests.
2. Add interval-based discovery and clean-disconnect handling.
3. Centralize port close, writer finish, and record-event ordering.
4. Update status snapshots and session explanation for waiting/stopped state.
5. Add regression tests, run the Recs suite, then run the USB lifecycle test.

## Additional Work Beyond The Prompt

None.
