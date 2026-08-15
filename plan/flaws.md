# Daemon Flaws And Risks

This review is for `recs` as a Raspberry Pi daemon in a larger local system.
Recording is the primary job. Network, GUI, control clients, disk management,
and device discovery must not block capture or hide a recording failure.

## Confirmed flaws

### Critical: disk stalls can lose capture blocks

`SourceRecorder` writes WAV data in the same process and loop that drains the
audio callback queue. A blocked `soundfile.write()` stops queue consumption.
After `recording.audio_buffer_seconds` (10 seconds by default), the callback
drops whole input blocks. Flash media can pause for that long during garbage
collection, heat throttling, unplug/replug, or an I/O error.

Work:

1. Measure write latency, queue high-water mark, and dropped frames per source.
2. Treat a sustained queue increase as a recording emergency before overflow.
3. Implement the disk-space and disk-failover plan before relying on removable
   flash media for a show.
4. Burn in each candidate USB disk at 18 channels for longer than a show.

### Critical: manifest fsync runs in the recorder loop

Every manifest record flushes and calls `fsync`. Device warnings, buffer
warnings, protocol errors, and control events therefore add synchronous storage
latency to the parent recorder loop. This can delay status/control processing;
on an unhealthy disk it can also cause control request threads to accumulate.

Work:

1. Keep append-only manifest recovery, but batch durability on a bounded timer.
2. Force a final fsync on orderly stop and record when a batch could not flush.
3. Ensure manifest failure becomes a visible recorder error without stopping
   source capture.

### High: control requests can wait forever

External RPC and GUI requests wait for the recorder loop to respond. A blocked
disk operation, deadlocked recorder loop, or process shutdown can leave each
client thread waiting indefinitely. Repeated clients can create unbounded
threads and pending requests.

Work:

1. Put a finite deadline on a queued control request.
2. Return a typed timeout error and remove the pending request on expiry.
3. Bound accepted control connections and expose the pending count in status.

### High: malformed startup settings restart the daemon without useful state

Invalid JSON, invalid saved attributes, unreadable settings, or an unwritable
settings path causes configuration loading/saving to raise. Systemd restarts
the daemon, but no status snapshot or retained error necessarily explains the
loop to Showco.

Work:

1. Validate all configured files before daemon installation/start.
2. On startup failure, write a small durable failed-status record containing the
   exception before exiting.
3. On a later settings-save failure, retain the recording configuration in
   memory, report the failure, and do not turn it into a silent API failure.

### High: no implemented removable-disk failover

The current `minimum_free_space` check stops the recorder. It does not pause,
switch to a larger newly inserted disk, distinguish system/removable reserve,
or resume after a replacement disk appears. This is especially dangerous with
a 64 GB USB disk.

Work:

1. Implement `plan/disk-space.md` before deployment.
2. Test full, unplugged, read-only, slow, and remounted disks while recording.
3. Write every alert, pause, switch, and resume to the manifest.

### High: source process failure can discard diagnostic detail

The child reports only selected `OSError`, `RuntimeError`, and `ValueError` as
a `SourceFailure`. Other exceptions terminate it. Parent reaping marks the
source failed but may only know that the process exited. Forced termination
after a two-second join can also discard pending source updates.

Work:

1. Send a structured final failure report for every child exception.
2. Record exit code, final frame count, and last callback timestamp.
3. Distinguish expected unplug, controlled stop, crash, and forced termination
in status and manifest events.

## Liveness and concurrency risks

### Source and event transport backpressure

Source-update and source-control helper threads can block on multiprocessing
pipes. Source updates coalesce, which preserves capture liveness, but hides
how long the parent has been unable to consume state. Event-subscriber writes
are synchronous and a stalled local client can delay publication from the
recorder thread.

Work:

1. Add explicit queue/pipe age and blocked-write metrics.
2. Use bounded, disconnectable event delivery so one subscriber cannot block
   recording/status publication.
3. Test a stopped parent, stopped child, and non-reading event client.

### Device query process has no backoff or bounded result queue

The long-running query child is restarted after five seconds without updates.
Repeated PortAudio failure can create restart churn. Its updates queue is
unbounded if the polling loop stops consuming.

Work:

1. Add exponential restart backoff and a status error containing the child exit
   code/stderr.
2. Keep only the newest device snapshot.
3. Verify that device querying never opens a capture stream or materially
   competes with the X18 source process.

### Device identity is based on mutable display names

Sources are keyed by device name. Replugging, ALSA renumbering, duplicate USB
names, or an edited alias can cause a device to be treated as a different
source, losing track layout/calibration association or attaching to the wrong
device.

Work:

1. Define and persist a stable device identity where the host API supplies one.
2. Display names remain user-facing labels only.
3. Test replug, duplicate X18-like names, and changed ALSA ordering.

## Operational risks

### Offline and network failure boundaries

Recs itself uses local sockets, but Showco and other suite programs may wait on
network actions or status checks. Recs must continue recording when Wi-Fi,
Ethernet, DNS, remote update, or streaming fails. Local status must not depend
on network reachability.

Work:

1. Exercise Recs with all network interfaces down.
2. Keep network clients out of recorder/source processes.
3. Require Showco to report stale local status separately from a failed network
   operation.

### Human error and conflicting services

Two daemon starts can leave one recorder running with failed IPC, while an
operator believes the other owns the system. A malformed control command is
now retained as an error, but repeated misuse can still flood errors and the
manifest.

Work:

1. Make singleton ownership visible in the status file and service response.
2. Rate-limit identical protocol/device/disk errors while preserving first and
   most-recent timestamps plus counts.
3. Provide an explicit preflight command that checks service state, writable
   output disk, configured devices, and settings before a show.

## Test matrix

Run these on the Pi with the X18 and target USB media:

1. No input devices at boot, then attach/detach/re-attach the X18.
2. Record 18 channels while repeatedly unplugging/replugging the USB disk.
3. Force disk-full, read-only, and multi-second write-stall conditions.
4. Stop consuming GUI/events/control connections and send malformed requests.
5. Kill source and device-query children at different points in a recording.
6. Restart Recs with malformed settings, missing profiles, and missing disks.
7. Disable Wi-Fi/Ethernet and restart Showco, streaming, and Recs independently.
8. Run for a full show duration and inspect manifests for frame gaps, source
   epochs, warning rates, and status freshness.

## Suggested order

1. Disk-stall observability and failover.
2. Bounded control/event liveness.
3. Source child failure diagnostics and device-query backoff.
4. Startup-failure status and preflight validation.
5. Stable device identity and full hardware fault-injection testing.

## Additional work beyond the prompt

None.
