# Device Online and Offline Lifecycle Plan

This plan addresses [issue #56](https://github.com/rec/recs/issues/56).

## Goals

- Keep recording when an expected input device goes offline.
- Start recording again when that device returns.
- Support devices that are offline when `recs` starts if a device reference file
  was supplied with `--devices`.
- Preserve cumulative recorded time, file size, file count, and level range across
  worker restarts.
- Keep alias, include, exclude, and track selection stable for the entire run.
- Shut down workers cleanly so buffered audio and open files are finalized.

## Non-goals

- Discover and add devices that were not in the initial expected device set.
- Infer the identity of two devices with the same name.
- Change track selection when a returning device reports a different channel count.
- Add reconnection behavior for file inputs.
- Persist recording state across separate invocations of `recs`.

## Current constraints

- `Cfg` resolves devices, aliases, includes, excludes, and tracks before recording
  starts. Re-resolving them after a device change could silently change the user's
  requested recording layout.
- `Recorder` currently creates one `SourceRecorder` process per source and exits as
  soon as any process dies.
- A Python `multiprocessing.Process` cannot be restarted. A returning device needs a
  newly constructed process.
- `SourceRecorder` and `ChannelWriter` hold transient stream and file state. They
  must be disposable.
- `FullState` already lives in the main process and applies incremental
  `ChannelState` updates. It is the correct owner for cumulative statistics.
- `Recorder.names` is currently a single startup snapshot, so the live display
  cannot reflect later device changes.
- `total_run_time` is counted inside each worker. Restarting a worker currently
  resets that count.

## Target design

### Permanent expected-device model

Resolve `source_tracks(cfg)` once at startup and retain that result for the entire
run. This is the permanent expected source and track set used by `FullState` and by
every replacement worker.

When `--devices` points to a reference JSON file, that file defines devices even if
they are offline at startup. Without a reference file, only devices visible during
startup can enter the expected set. Returning devices are matched by the existing
device-name identity rule.

File sources continue through the current fixed-process path and do not participate
in hardware polling.

### Main-process worker owner

Introduce a small `SourceProcess` owner in the main process. Each owner retains:

- The immutable source and selected tracks.
- The raw configuration needed to construct a worker.
- The current `multiprocessing.Process`, parent connection, and stop signal, if any.
- A lifecycle state such as offline, starting, online, stopping, or failed.

Starting an owner always creates a fresh pipe, stop signal, and process. Stopping an
owner requests graceful shutdown, closes its connection, joins it, and only
terminates it if graceful shutdown cannot complete within a bounded timeout.

`SourceRecorder` remains the child-process recording implementation. It receives a
stop signal and checks it in the existing queue polling loop. Leaving its context
stops the input stream and finalizes every `ChannelWriter`.

### Device polling and reconciliation

Run `device.query_devices()` on a polling thread using `sleep_time_device` as the
poll interval. The polling thread publishes complete snapshots of available input
devices, keyed by device name, to a thread-safe queue. Devices with no input channels
are omitted. The thread does not create, stop, or mutate worker processes.

The main `Recorder` loop consumes the latest snapshot and performs reconciliation:

- An expected device present in the snapshot with no worker is started.
- An expected device absent from the snapshot with a worker is stopped.
- Devices outside the expected set are ignored.
- A device whose reported channel count is lower than its configured tracks is
  treated as unavailable and reported as an error rather than opening an invalid
  stream.

Keeping reconciliation in the main loop avoids concurrent mutation of the connection
set while it is passed to `multiprocessing.connection.wait()`.

### State and messages

Keep the existing child-to-parent incremental `ChannelState` messages. Do not move
cumulative totals into workers.

Extend `FullState` with an explicit source lifecycle update. When a source goes
offline, clear transient channel state such as `is_active` and volume while retaining
cumulative recorded time, file size, file count, and amplitude range. When it returns,
new deltas continue accumulating into the same entries.

Replace the static `Recorder.names` snapshot with the reconciler's current online
name set. `FullState.rows()` then reports the source as offline immediately after the
main loop processes an unavailable snapshot.

### Recorder lifetime

The main loop must no longer depend on `all(process.is_alive())`. It remains alive
when zero expected hardware devices are online so that the polling thread can detect
a returning device.

Move `total_run_time` ownership to `Recorder`. Use the existing main-process elapsed
clock and request shutdown when the configured duration is reached. Check the
deadline once per main-loop iteration so recording can be slightly longer than the
requested duration, but not intentionally shorter. Worker restarts must not reset the
deadline.

## Implementation phases

Each phase should be a separate commit with the full existing test suite, Ruff, and
ty passing.

### Phase 1: Make state lifecycle-aware

1. Add source online/offline state to `FullState`.
2. Remove the `devices` argument from `FullState.rows()` and derive status from its
   maintained lifecycle state.
3. On an offline transition, clear only transient channel state.
4. Add focused tests proving that cumulative totals survive an offline and online
   cycle.

### Phase 2: Encapsulate the existing worker process

1. Add `SourceProcess` as the sole owner of a worker process and connection.
2. Move process construction out of `Recorder.__init__` into `SourceProcess.start()`.
3. Add a stop signal to `SourceRecorder` and implement graceful stop and join.
4. Keep startup behavior static in this phase so existing end-to-end behavior remains
   unchanged.
5. Add tests using fake processes and connections for start, stop, and replacement.

### Phase 3: Make Recorder's worker registry dynamic

1. Replace the parallel `processes` and `connections` lists with source-name keyed
   `SourceProcess` owners.
2. Build the connection list from currently running owners for each wait call.
3. Route each received delta to the permanent `FullState`.
4. Remove the exit-on-first-dead-process condition.
5. Move `total_run_time` enforcement to the main loop.

### Phase 4: Poll and reconcile hardware devices

1. Add the polling thread and snapshot queue.
2. Start only expected devices that are present in the first snapshot.
3. Reconcile later snapshots in the main loop.
4. Stop missing device workers and start fresh workers for returning devices.
5. Stop and join the polling thread before shutting down remaining workers.

### Phase 5: Regression and failure testing

1. Simulate an expected device that is online, offline, then online again.
2. Verify that two distinct worker process instances are created.
3. Verify that open files are finalized during the offline transition.
4. Verify that cumulative statistics continue from their previous values.
5. Verify that an expected device offline at startup can appear later when a reference
   device file is used.
6. Verify that an unexpected device is ignored.
7. Verify that file-source recording follows the unchanged one-shot path.
8. Verify shutdown while all hardware devices are offline.
9. Run the existing WAV end-to-end regressions unchanged at 48,000 samples per second.

## Acceptance criteria

- Pulling one expected device does not stop recording from other expected devices.
- The live display marks the missing device offline without losing its totals.
- Reconnecting the device creates a new process and resumes recording its selected
  tracks.
- Alias and include/exclude results remain identical before and after reconnection.
- A device listed in `--devices` may be absent at startup and begin recording later.
- Unknown devices do not alter the configured track set.
- Program shutdown leaves no worker processes or polling threads running and no audio
  files open.
- `total_run_time` covers the whole invocation rather than resetting per worker.
