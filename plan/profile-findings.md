# Profiling findings

Analysis date: 2026-11-02.

## Run and interpretation

The profile was recorded with:

```sh
uv run --python 3.15 recs --profile-fake=18:10 --total-run-time 60
```

Reports are in `recs-profile-wyl0sfgo/`. The analysis covered `profile.html`
and all subprocess reports, including recording workers `profile_27644.html`
and `profile_27645.html`.

This run shows substantial spare capacity on the machine tested. It does not
establish performance on the Raspberry Pi or with real audio devices.

These are wall-time samples, not CPU measurements. Sleeping, waiting for audio,
and blocking inside native code all count. Summing across threads also counts
concurrent time multiple times. Reported seconds below are sample-count estimates,
not exact operation timings. Sampling failures were approximately 7.7% in the
parent and 2.5% and 2.0% in the two recording workers.

The recording workers ran for approximately 60 seconds:

| Sampled activity | Worker 27644 | Worker 27645 |
| --- | ---: | ---: |
| Waiting for incoming audio | 55.67 s | 57.00 s |
| Native audio encoding/writing | 1.25 s | 0.83 s |
| Deciding whether to record | 0.65 s | 0.39 s |
| Fake signal generation: positions and sine calculation | 0.75 s | 0.69 s |

The processing threads spent approximately 95% and 97% of their successfully
sampled time waiting for audio. Fake signal generation runs on separate threads.

## Findings

### 1. Automatic inspection was a significant startup cost, now removed

The parent spent approximately 7.19 sampled seconds in
`Recorder._report_unfinished_sessions`, including 5.11 seconds reading recording
documents. Parsing, schema construction, and logging contributed to this.

This profile predates removal of automatic recovery inspection in commit
`20733c3`. A fresh profile should show that entire branch gone. This is the
clearest improvement already made.

### 2. Audio encoding/writing is the largest actual recording hotspot

Across the two workers, approximately 2.07 sampled seconds were inside
SoundFile's native I/O call. That combines encoding and file I/O; this profile
cannot separate them.

A useful experiment would combine adjacent audio blocks into larger writes,
while keeping silence detection at its existing resolution. That could reduce
Python/C calls and per-write metadata updates in `ChannelWriter._write_blocks`
in `recs/audio/channel_writer.py`.

Combining blocks introduces copying and some buffering, so the tradeoff needs
measurement before adoption. There is no evidence here that the device's
callback block size should change. Continue letting the device and driver choose
it unless the user explicitly specifies it.

### 3. Level detection is the next meaningful audio cost

Approximately 1.04 sampled seconds were spent deciding whether to record. Most
of that is NumPy's minimum and maximum reductions in `Block` in
`recs/audio/block.py`.

Those values are already cached within each block, so this is not repeated
scanning of the same `Block` through its properties.

One candidate is computing channel extrema once for the whole device block,
then deriving each track's level from those results. That could reduce small
reduction calls and duplicate work when tracks share channels. It must preserve
the existing detection semantics. Replacing the calculation with RMS or absolute
peak would change recording behavior.

### 4. Disk monitoring does unnecessary work before its interval check

The parent spent approximately 0.42 sampled seconds in disk monitoring. About
0.375 seconds were in resolving paths and finding mounted disks.

In `Recorder._monitor_disk_space` in `recs/runtime/recorder.py`, mount discovery
happens before `DiskSpaceController.monitor_disk_space` checks whether another
measurement is due.

Moving that work under an appropriate monitoring interval is a small, concrete
optimization candidate. Immediate checks on write failures and card replacement
must remain available.

### 5. Discovery subprocesses are deliberately replaced every five seconds

The many short-lived profiles are explained by
`DEVICE_REFRESH_INTERVAL = 5.0` in `dvice/poller.py`. Their profiles are
overwhelmingly sleeping rather than doing expensive audio work.

For fake devices, that replacement achieves little because the inventory is
fixed. Bypassing periodic replacement for fake discovery would reduce process
churn and profile clutter. Changing real-device refresh behavior needs a separate
look at why dvice requires it.

### 6. The fake generator adds measurable work of its own

Position-array creation and sine generation account for approximately 1.43
sampled seconds across the two generator threads, excluding callback handling
and conversion. This cost does not exist with real devices.

Precomputing repeating synthetic audio in `recs/cfg/profile_devices.py` could
make the fake test better isolate recording costs, but it would change the test
workload.

## Recommended next steps

1. Obtain a fresh baseline with automatic inspection removed.
2. Address disk-monitor scheduling.
3. Benchmark larger file writes, preserving detection resolution.
4. Evaluate level-detection changes after measuring those improvements.
5. Consider reducing fake-discovery process churn and fake-signal generation
   overhead to improve the profiling workload itself.

Future profiling should include silence and sound transitions. This
continuous-tone run does not exercise segment opening, closing, and preroll
behavior well. Fake recordings should use an explicitly isolated output
directory so they do not enter normal backup/upload workflows.

These are findings and proposed experiments, not implemented optimizations.
No additional recording was run during the analysis.
