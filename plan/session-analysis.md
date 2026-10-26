# Session fragmentation and missing audio on t.local

Investigation date: 2026-10-26. This report records observations from the baccy
backup investigation for analysis by recs. No recording settings were changed,
no audio was edited, and recs was not restarted during the investigation.

## Main finding

The user reports that X18 channels 7 and 8 were running almost continuously.
Nevertheless, one inspected session contains 202 FLAC files for channels 7–8.
Channels 17–18 have 42 surviving FLAC files containing only about 71 seconds of
audio across a span of about five minutes, with substantial intervals between
files. The current sensitive threshold and 20-second quiet timeout do not, by
themselves, adequately explain this fragmentation.

The journal contains buffer-overflow events and does not consistently describe
the surviving audio files. Capture continuity, file lifecycle reporting, and
threshold behavior need separate investigation. A high threshold is a hypothesis,
not an established diagnosis. Input levels and audio samples were not analyzed.

## Recording tree and session examined

The remote mounted recording root is:

```text
t.local:/mnt/recordings/recs
```

A filesystem inventory found 2,244 regular files, including 2,135 FLAC files,
across 29 session directories dated October 16–25, 2026. The tree occupied about
6.3 GB as reported by `du -sh`; this is a rounded filesystem usage figure.
These counts cover the whole tree, not one show. Session directories must not
be assumed to correspond one-to-one with shows.

The detailed analysis concerns:

```text
/mnt/recordings/recs/-default-/2026/10/16/22-29-23
```

Its version-5 journal header reports `started_at = 2026-10-16T20:29:23.728Z`.
The footer reports `ended_at = 2026-10-16T20:51:54.358Z` and a session duration
of about 22 minutes 31 seconds. Filename times below are local times on October
16, consistent with Europe/Paris, UTC+02:00.

This directory contains 451 regular files. Grouping its surviving FLAC filenames
by device and channel pair gives:

| Device | Channels | FLAC files |
| --- | --- | ---: |
| X18 | 3–4 | 203 |
| X18 | 7–8 | 202 |
| X18 | 17–18 | 42 |

The statement about nearly continuous activity on channels 7–8 comes from the
user. It has not been independently verified by listening or signal analysis.

## Channels 17–18: estimated gaps

All 42 existing channel-17–18 FLAC headers were inspected with `soundfile.info`
on the server. Durations were calculated as `frames / sample_rate`. The files
are stereo at 48,000 samples/second. No audio samples were decoded for this
analysis.

For each adjacent pair of files, the estimated gap was calculated as:

```text
next filename start time - (previous filename start time + previous duration)
```

The filename timestamps have one-second resolution. Consequently, individual
gap estimates have roughly one-second uncertainty and are not sample-accurate.
Small apparent overlaps from this calculation are not proof of overlapping
recorded samples. This method assumes filenames retain their recs-generated
start timestamps; no renaming was performed during the investigation.

Results within the first-to-last surviving file span:

- First file starts at approximately 22:41:17.
- Last file ends at approximately 22:46:26.
- Total span: 309.2 seconds, about 5 minutes 9 seconds.
- Total audio duration: 71.242 seconds.
- Difference between span and summed audio duration: about 238 seconds,
  or 3 minutes 58 seconds.
- There are 41 boundaries between the 42 files.
- Median estimated gap: 2.55 seconds.
- Seven estimated gaps exceed 10 seconds.

The longest estimated gaps are:

| Approximate interval, local time | Estimated gap |
| --- | ---: |
| 22:42:07–22:43:02 | 54.6 seconds |
| 22:43:03–22:43:26 | 23.0 seconds |
| 22:45:14–22:45:30 | 15.5 seconds |
| 22:43:37–22:43:51 | 13.9 seconds |
| 22:44:39–22:44:53 | 13.5 seconds |
| 22:43:59–22:44:12 | 13.0 seconds |
| 22:46:03–22:46:16 | 12.7 seconds |

The approximately 238 seconds are intervals between surviving files, not a
measurement of how much audible material was lost. The contents of those
intervals are unknown. Time before the first surviving file and after the last
is excluded from this calculation.

## Journal inconsistencies and overflow evidence

The inspected session journal is:

```text
/mnt/recordings/recs/-default-/2026/10/16/22-29-23/session-record.jsonl
```

Of the 42 surviving channel-17–18 files, 18 have no matching `file_started`
record with `source_channels = [17, 18]` and the same relative path. One existing
file has two such start records. Records explicitly carrying those channel
numbers include 370 `file_started`, 250 `file_discarded`, and 11 `file_finished`
events. Those counts should not be treated as counts of unique surviving files.

An initial calculation using only those 11 finished records suggested a much
larger gap of about 138 seconds. That calculation was incomplete because other
surviving files fill parts of that interval. It was superseded by the 42-file
header-based calculation above and must not be used as a loss estimate.

The journal also contains X18 `buffer_overflow` events. For example, events at
`2026-10-16T20:30:18.287Z` report `dropped_blocks = 3`, `dropped_frames = 1152`,
and `max_queued_seconds = 9.984`. Later nearby events report a queue reaching
10 seconds. Some entries repeat, so dropped-frame values must not simply be
summed without establishing their semantics and deduplicating appropriately.

The presence of overflow events is verified. Their exact contribution to the
channel-17–18 gaps, or to channel-7–8 fragmentation, has not been established.
The session also contains `recs-recovery-report.toml`; its contents have not
yet been analyzed.

## Current threshold and timing settings

The following values were read directly from the running daemon on t.local
using `recs control get recording.FIELD`:

| Field | Current value |
| --- | --- |
| `noise_floor` | `70.0` |
| `channel_noise_floors` | `{}` |
| `stop_after_quiet` | `20.0` seconds |
| `quiet_before_start` | `10.0` seconds |
| `quiet_after_end` | `10.0` seconds |
| `record_everything` | `false` |

In `recs/cfg/time_settings.py`, `db_to_amplitude(db)` returns `10 ** (-db / 20)`.
Thus a setting of 70 corresponds to an amplitude threshold of approximately
0.000316 of full scale, or 0.0316%, conventionally expressed as −70 dBFS.
Increasing the positive setting to 80 lowers the threshold to −80 dBFS and
makes detection more sensitive.

`recs/audio/channel_writer.py` compares `block.volume` against that converted
noise floor. Its `_noise_floor` function uses a matching per-track override
when present, otherwise the configured global noise floor. No channel-specific
overrides were returned by the live configuration query.

These are current settings, not a historical snapshot from October 16. The
daemon installation arguments currently contain no explicit noise-floor option,
but that does not prove historical defaults, profile values, or live settings.
Historical effective settings still need to be established.

The current channel-writer implementation can close a file after sufficient
quiet, on a timing discontinuity, on stopping, or at configured file length/size
limits. Those are candidate mechanisms to trace, not conclusions about which
one caused the inspected session's fragmentation.

## Backup and watcher context

Baccy previously scanned only `~/recs` and missed `/mnt/recordings/recs`.
Support for extra recording roots was added and deployed. Successful copies
from the mounted root were observed, including October 22 and 25 journals and
FLAC audio. The October 25 `23-39-08/session-record.jsonl` copy was checked
against the remote original using SHA-256 and matched. Full backup completion
has not been verified.

The backup monitor also encountered stale recs instance registrations. A prior
PID was reused by another process, while old registrations still pointed at the
current daemon's control endpoint. The listening watcher rejected the identity
mismatch and reported `listening: null`. Identified stale registrations were
moved into `~/.local/state/recs/instances/stale/`, preserving the current daemon
registration. The watcher then reported `listening: false`, without restarting
recs. This was an operational workaround, not a persistent recs code fix.

The current daemon was observed as PID 1187 during the October 26 investigation.
No claim is made that it is the same process that recorded the October 16
session. Backup work performed on October 25–26 cannot explain capture events
already recorded on October 16.

## Evidence locations and methods

Primary evidence remains on t.local at the remote paths above. Collection used
read-only SSH commands: `find` for file inventories, `du -sh` for tree usage,
`cat` for the journal, `soundfile.info` for FLAC headers, and `recs control get`
for live settings. Reading headers is not an integrity check or a listening test.

Temporary local evidence from this investigation is available at:

- `/private/tmp/baccy-session-20261016-222923.jsonl`: copied session journal.
- `/private/tmp/recs-17-18-flac-info.jsonl`: frame counts and sample rates for
  all 42 surviving channel-17–18 files.
- `/private/tmp/recs-gap-estimates.py`: final filename/header gap calculation.
- `/private/tmp/recs-remote-flac-info.py`: header inspection script, executed
  through the server's existing recs Python environment.
- `/private/tmp/baccy-threshold-state.txt`: installation/status inspection;
  the live threshold values were returned separately by the control queries.

These temporary files are aids to reproduction, not durable archived evidence.
They were not added to the repository. The earlier exploratory scripts
`analyze-recs-gaps.py` and `analyze-recs-existing-gaps.py` in the same temporary
directory are not the final calculation and have the limitations noted above.

Local implementation references inspected were
`recs/audio/channel_writer.py`, `recs/cfg/time_settings.py`,
`recs/cfg/sections.py`, `recs/recording/session_record.py`, and
`recs/daemon/listening.py`. These describe the checkout inspected during the
investigation, not a verified reconstruction of the recording-time revision.

## Questions for recs analysis

1. Which closure mechanism caused each channel-7–8 and channel-17–18 file split:
   silence timeout, capture timing discontinuity, duration/size limit, stop, or
   another path?
2. What were the effective thresholds and timing settings during this session,
   including device profiles and any live updates?
3. Why do surviving files lack matching start records, and why do lifecycle
   events outnumber surviving files so heavily? Inspect the recovery report
   and any filename reuse or recovery behavior before trusting the journal as
   a complete file inventory.
4. How do overflow events and dropped-frame accounting align with the actual
   recorded intervals? Avoid summing repeated or cumulative counters blindly.
5. Are additional journals, recovery evidence, or files able to account for
   audio absent from the intervals analyzed here?
6. Why do stale instance registrations survive process exits or reboots, and
   how should the listening watcher distinguish PID reuse from a live recs
   instance without losing its fail-closed behavior?

No implementation changes are proposed as established fixes by this report.

## Additional work beyond the prompt

None.
