# Always-On MIDI Recording

## Scope

Add always-on MIDI recording beside the existing audio recorder. MIDI silence
does not need silence detection or segmentation, so the first version records
every received MIDI message into one file per MIDI input for the whole session.

The session output layout changes from putting audio files directly in the
session directory to separating recorded media by kind:

```text
/mnt/openloop/recs/
  session-record.jsonl
  audio/
    X18-1-2.wav
  midi/
    Launchkey.mid
```

For a patterned output directory, the record remains at the root of the session
directory chosen by the existing pattern. Audio paths move under `audio/`, and
MIDI paths go under `midi/`.

## Goals

- Record all selected MIDI inputs whenever a recording session is active.
- Keep MIDI capture independent from the audio callback and audio writers.
- Write one MIDI file per input device per session.
- Preserve enough timing information for later playback and session review.
- Record MIDI lifecycle and file records in the existing record.
- Keep the first version local, file-based, and free of database state.

## Non-Goals

- Do not split MIDI files by silence, duration, markers, or file size yet.
- Do not synchronize MIDI to audio sample frames in the first version.
- Do not add MIDI playback or editing in this plan.
- Do not add MIDI learn, routing, filtering, or transformation yet.
- Do not merge all MIDI devices into one file until there is a clear need.

## Dependency

Use `mido` for MIDI device enumeration, input ports, messages, and MIDI file
writing. Add it in its own dependency commit because repository policy keeps
dependency changes separate.

Timing source:

- Prefer `mido` message timing when the input backend provides useful deltas.
- Otherwise use `time.time()` at receive time and compute deltas from the
  previous recorded MIDI event on that input.
- Store the selected timing source in the record so later diagnostics know
  whether the file used backend timing or system receive timing.

## Configuration

Add a `Midi` config section to `Cfg`:

- `midi: bool = True`
  Enable MIDI recording by default.
- `midi_include: list[str] = []`
  Optional MIDI input name prefixes or aliases to include.
- `midi_exclude: list[str] = []`
  Optional MIDI input name prefixes or aliases to exclude.
- `midi_timing: Literal['mido', 'system'] = 'mido'`
  Use backend timing when useful, or force `time.time()` deltas.

Keep this separate from audio device selection. Audio `include` and `exclude`
should continue to mean audio sources only unless a later design introduces a
unified source selector.

## File Format

Write standard MIDI files with one track per input file:

- Use type 0 unless type 1 becomes necessary.
- Use a fixed ticks-per-beat value of 960.
- Convert seconds to ticks using a fixed tempo meta event.
- Write input/device name metadata at the start of the track.
- Append each received MIDI message with a delta time since the previous
  recorded message.

The writer should keep an in-memory `mido.MidiTrack` for the current session and
write the `.mid` file at shutdown. This is acceptable for the first version
because MIDI event volume is small compared with audio. Add a record warning
if the file cannot be written.

If later tests show very high event counts, replace the writer with a streaming
SMF writer or a simple JSONL MIDI event log. Do not add that complexity in the
first version.

## Runtime Architecture

Add a MIDI package, likely `recs/midi/`, with these responsibilities:

- `midi/device.py`
  Enumerate input ports through `mido.get_input_names()`, apply include/exclude
  selection, and create stable source keys.
- `midi/recorder.py`
  Own the MIDI source lifecycle. Open selected input ports, poll messages, and
  forward them to writers.
- `midi/writer.py`
  Accumulate received messages and write one `.mid` file per source at session
  end.

Integrate MIDI into `Recorder` at the orchestration level, not in
`SourceRecorder` or `ChannelWriter`. Audio and MIDI should be sibling source
pipelines under the session:

```text
Recorder
  RecordingSession
  DeviceLifecycle        audio hardware and file sources
  MidiRecorder           MIDI input ports and MIDI writers
```

`Recorder._run()` should poll MIDI once per main loop iteration after control
requests and before sleeping. MIDI polling must be non-blocking. If mido backend
support requires callbacks or threads, keep the thread local to `MidiRecorder`
and drain a bounded queue from the main loop.

## Session Paths

Add helpers in `recording_paths.py`:

- `audio_directory(output_directory: str, timestamp: float) -> Path`
- `midi_directory(output_directory: str, timestamp: float) -> Path`

Then update audio path generation so recorded audio goes under `audio/`.
Examples:

- session directory: `/mnt/openloop/recs`
- session record: `/mnt/openloop/recs/session-record.jsonl`
- audio: `/mnt/openloop/recs/audio/X18-1-2.wav`
- MIDI: `/mnt/openloop/recs/midi/Launchkey.mid`

Make the path change deliberately and update tests that currently expect audio
files beside the record.

Disk switching should keep the same structure in the new session directory. A
continued session after a disk switch should have its own `audio/` and `midi/`
directories, with record continuation links unchanged.

## Session Record Entries

Extend file entries in the session record so MIDI files can be represented without pretending
they are audio:

- Add a `media_type` field to file records: `audio` or `midi`.
- Keep existing audio fields for audio files.
- Add MIDI-specific optional fields:
  - `quantity_count`
  - `timing_source`
  - `midi_port`

Add MIDI lifecycle events:

- `midi_source_started`
  MIDI input opened.
- `midi_source_failed`
  MIDI input could not open, died, or raised while polling.
- `midi_file_finished`
  MIDI file was written at session shutdown. This can also be represented as a
  `file_finished` record with `media_type='midi'` if that keeps scanners simpler.

The session browser, record validator, and explain command should distinguish
audio and MIDI files in their summaries.

## Error Handling

MIDI failures should not stop audio recording.

- If a MIDI input cannot open, record a warning and continue.
- If a MIDI input fails while recording, close that input, record a
  `midi_source_failed` event, and continue audio recording.
- If writing the final `.mid` file fails, record a record warning before the
  record closes if possible.
- If there are no MIDI devices, do not warn by default. Always-on MIDI should be
  silent when there is nothing to record unless the user explicitly selected a
  MIDI input.

## CLI and Status

Expose MIDI state in existing status surfaces:

- `recs daemon status`
  Include selected MIDI inputs, whether each is open, message counts, and last
  message timestamp.
- `recs sessions`
  Count audio files and MIDI files separately.
- `recs session show`
  Show MIDI device names and message counts.
- `recs record check`
  Check referenced MIDI files exist and have a plausible nonzero size when
  `quantity_count` is nonzero.
- `recs explain`
  Report selected MIDI input failures separately from audio failures.

Do not add separate `recs midi ...` commands in the first implementation unless
needed for tests.

## Implementation Order

1. Add `mido` as a dependency in a dedicated commit.
2. Add path helpers and move audio output into `audio/`, updating record and
   session-browser tests.
3. Add record support for `media_type='audio'` and `media_type='midi'` file
   records.
4. Add MIDI config fields and MIDI input selection tests.
5. Add `MidiWriter` unit tests for converting timed mido messages to a `.mid`
   file.
6. Add `MidiRecorder` with fake mido ports in tests, covering open, poll,
   message count, close, and failure warnings.
7. Integrate `MidiRecorder` into `Recorder` start, loop, status, and shutdown.
8. Update `recs sessions`, `recs session show`, `recs record check`, and
   `recs explain` for MIDI file records and MIDI source failures.
9. Add an end-to-end regression using fake MIDI input ports and audio disabled
   or mocked.
10. Runtime-test on macOS and Raspberry Pi with at least one USB MIDI device.

## Test Plan

- Unit-test MIDI device selection without real hardware.
- Unit-test system-time delta conversion with a fake clock.
- Unit-test mido-timing mode with fake messages that provide timing values.
- Unit-test final `.mid` file writing and reopening through mido.
- Unit-test that MIDI input failure records warnings without stopping audio.
- Regression-test that audio files move under `audio/`.
- Regression-test that MIDI files are written under `midi/`.
- Regression-test record validation on mixed audio and MIDI records.
- Manually verify real MIDI recording with a connected controller.

## Migration Notes

The session record identifies every file's medium explicitly.
This keeps `recs sessions`, `recs session show`, `recs record check`, and
`recs explain` useful for already-recorded material.

The audio path move is not backward compatible for tests and new sessions, but
existing records with old audio paths must remain readable because session
tools operate on paths recorded in the record.

## Open Questions

- Should MIDI be enabled by default in daemon installs, or only in normal runs?
  This plan assumes enabled by default.
- Should an explicitly selected but missing MIDI input be a startup error or a
  warning? This plan assumes warning, because audio capture is still valuable.
- Should MIDI input aliases share the existing alias config, or get a
  MIDI-specific alias section? This plan keeps selection separate but does not
  decide alias storage yet.

## Additional work beyond the prompt

None.
