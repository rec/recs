# Command-line profiling

Run recs using Python 3.15, which includes Tachyon (`profiling.sampling`):

```sh
uv run --python 3.15 recs --profile
uv run --python 3.15 recs --profile-fake=18:10 --total-run-time 60
```

`--profile` uses the normal device discovery and recording configuration.
`--profile-fake` replaces audio input discovery with the requested devices and
also enables profiling. Each colon-separated positive integer specifies one
input device's channel count. `18:10` supplies two devices. Empty components,
zero, negative numbers, and non-integers are rejected.

Fake audio is paced in real time at 48 kHz, with 960-frame callbacks by default.
Each channel carries a continuous 0.1-amplitude sine wave at a distinct frequency.
An explicitly configured audio blocksize overrides that fake callback size.
This exercises capture queues, detection, per-source child processes, writers,
and encoding. Signal generation itself also appears in the profile. It does not simulate hardware overruns, driver callback variation,
clock drift, disconnects, or silent-channel workloads. Device/channel selection
and other recording options still apply. Fake input can write real recordings;
use `--dry-run` to measure detection without file output, or select an output
location with `--output-directory` for writer/encoder profiling.

Each invocation prints a unique `recs-profile-*` directory in the current
working directory. Tachyon writes HTML flame graphs there, including separate
files for Python child processes. All threads and descendant processes are
sampled at Tachyon's default 1 kHz wall-clock rate. Inspect source-process graphs
for capture/detection/writing costs and the parent graph for orchestration.
Waiting threads appear in wall-clock profiles; sample percentages are not CPU
utilization. Stop normally or set `--total-run-time` to finish and save reports.
No browser opens automatically.

Normal recording continues to support Python 3.13. Profiling flags require
Python 3.15 for both recorder and profiler; they never silently change Python
versions. Run from a terminal with a valid locale. The operating system must
allow Tachyon to inspect child-process memory. On macOS, this may require an
appropriately signed/developer-enabled Python installation or elevated
permissions. Check profiler permissions before profiling a performance.

Reference: [Python's Tachyon documentation](https://docs.python.org/3.15/library/profiling.sampling.html).
