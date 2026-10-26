# Preserve performances while suppressing silence

## Objective

Silence suppression is fundamental to recs. At the last show, 10 of 18
channels were silent throughout; enabling FLOW 8 would have made that 20 of
28. Archiving all those channels continuously would defeat the system's
purpose. `record_everything` must remain an explicit opt-in, not the default.

Performances are unique. Disk space is cheap relative to losing a performance.
Discard confidently identified silence and preserve uncertain material. This
requires a bounded decision buffer and reliable segmentation during capture,
not recording hours of silence for later analysis.

This document proposes the next capture design. The explicit block-size
override and restoration of driver-selected blocks are already implemented.
Implementation progress is recorded below; the remaining architectural work
and hardware qualification are still pending.

## Implementation progress

Implemented in the first follow-up:

- Sample-exact preroll and tail trimming, including partial driver blocks and
  the corresponding source-frame/timestamp adjustments.
- Retention of files containing activity, explicit recording requests, or
  uncertain material even when shorter than `shortest_file_time`.
- Conservative retention of delivered audio after known frame gaps or backend
  input-status warnings, followed by normal suppression once quiet is observed.
- Queue capacity and queue-duration reports based on actual queued frames,
  independent of driver block sizes. System-memory probes are performed at
  setup and by the consumer rather than inside the callback.
- Regression cases for exact padding with irregular blocks, frame-based queue
  limits and loss accounting, and 10-of-18 / 20-of-28 silent-channel layouts.

Implemented in the detector/batching follow-up:

- Consumer-owned windows on a fixed source-frame grid. The existing per-track
  peak-to-peak metric now sees complete sample windows, not individual driver
  callbacks. This avoids one-frame callbacks always measuring zero range.
- `silence_window_seconds`, initially 0.05 seconds: 50 ms covers one cycle at
  20 Hz. Window lengths are rounded to source frames with a two-sample minimum.
- `processing_batch_seconds`, initially 0.1 seconds: bounds each consumer drain
  and the wait for an incomplete window. It must be at least the detector
  window duration. Neither setting requests a hardware callback size.
- Partial-window flushes on stalled input, known gaps, backend warnings,
  configuration/layout/session transitions, and shutdown. Incomplete nonzero
  material above the track's threshold is retained conservatively; exact-zero
  silent tracks do not become recordings merely because a window is short.
- Exact sample/frame/status positions when processing batches split a larger
  driver block. Unprocessed windows survive a temporary write failure for
  existing recovery/failover handling.
- Callback shutdown and queue draining before writer closure, including an
  interrupted main loop. Capture-child termination signals request a stop
  without interrupting copying/writing. The final partial window is evaluated
  before closing; an explicit run-duration limit is enforced in source frames.
- Widened arithmetic before integer peak subtraction, preventing loud int16 or
  int32 samples from overflowing into a negative measured amplitude.
- Full-path regressions comparing retained samples across callback partitions
  and batch bounds, plus stop, interruption, setting changes, and write recovery.

These duration defaults are explicit initial algorithm/latency choices, not
Pi-tuned throughput results. Timing diagnostics and Pi qualification remain
necessary before declaring show readiness. Native buffering or stronger
isolation remains conditional on measured need.

## Evidence and current behavior

The October 16 session in [session-analysis.md](session-analysis.md) shows
rapid file churn, surviving files without starts, contiguous capture frames
split into different files, and cumulative application-buffer drops. It covers
22 minutes, not the entire four-hour performance. The recording-time binary
and full callback-size distribution have not been recovered.

The recent continuity fix removes timestamp-based splitting, retains pending
quiet until a split decision, merges activity with touching padding, preserves
preroll after closing, and reports creations independently of surviving files.
It does not fix buffer overruns. Silence suppression remains part of capture;
short-file deletion now excludes active or uncertain material.

The old hard-coded 20 ms capture request is removed. Driver-selected blocks
are the default. `audio.capture_block_frames` / `--capture-block-frames` is a
startup-only explicit override in frames per callback, not milliseconds. It
applies to hardware capture, not offline file reading. No power-of-two or
even-length constraint is imposed.

## Required behavior

1. Suppress confidently identified silence independently on each selected
   track. Respect explicit channel exclusions, mute policy, band mode, and the
   user's stop command. An active track must not cause unrelated silent tracks
   to be stored unless the user explicitly enabled linked recording.
2. Retain undecided samples in a bounded buffer until activity, quiet timeout,
   and padding determine what to write. Keep material when the evidence is
   uncertain. Never classify missing samples as silence.
3. Make capture segmentation reliable. Activity whose padding touches or
   overlaps belongs to one continuous performance. Timing jitter and driver
   block boundaries must not cut it into fragments.
4. Distinguish storage chunks from performances. A long performance may span
   many storage files without an audible boundary or an edit decision.
5. Never split, drop, repeat, or invent samples to make wall-clock timestamps
   appear smooth. Never conceal loss by concatenating a missing interval away
   in the logical recording timeline.
6. Make shutdown close files and finish the journal promptly. Hashing, payload
   inspection, rendering, and compression conversion remain deferred work.

## Silence decisions and storage

Continue receiving the selected device inputs, but write only retained
performances, their padding, and uncertain material. Keep the existing
per-track channel mapping and independent silence decisions. Do not introduce
one persistent device-wide file that stores silent channels alongside active
ones. A deliberately linked stereo track follows its configured track policy.

Before activity, retain only the configured preroll in memory. A channel that
stays confidently silent for four hours must not accumulate four hours of
audio on disk or in memory. Activity opens a file with the retained preroll.

While a performance is active, retain all pending quiet until it either rejoins
activity or exceeds both `stop_after_quiet` and the combined before/after
padding. If activity resumes before that boundary, write the whole intervening
interval once. Otherwise write the quiet immediately following the sound,
close the performance, and keep only the latest preroll for another start.
Suppress the remaining confidently quiet interval. Reuse the corrected
segmentation logic rather than creating a second implementation.

Record uncertainty with the affected track and sample range where known.
An ambiguous signal classification or a capture discontinuity must not trigger
short-file deletion or trim away surrounding available material. Retain that
material and its evidence. Wall-clock jitter alone does not make an otherwise
confidently silent track active or disable silence suppression indefinitely.
After uncertainty, resume suppression when a fresh, fully observed quiet
decision window establishes silence.

For `shortest_file_time`, duration alone cannot establish that a fragment
contains no useful audio. A short fragment with detected activity or timing/loss
uncertainty must be retained. Any automatic discard needs affirmative evidence
that the candidate is confidently suppressible, with lifecycle evidence kept.

Storage size/duration limits may rotate an active performance without declaring
a performance boundary. Preserve exact frame adjacency across those files.
A device restart gets a new capture identity; do not infer sample continuity
across independent device clocks. Keep the user's selected recording format.
Compare PCM and FLAC throughput during qualification before proposing any
format-policy change; continuous archiving and deferred compression are not
requirements of this plan.

## Driver blocks and processing batches

Leave the hardware callback size unspecified unless the user requests one.
The host is allowed to deliver arbitrary positive frame counts, including
one-frame blocks and odd sizes. A driver block is not a processing unit or a
storage-file boundary.

Keep the callback limited to copying delivered samples into capture-owned
storage and recording compact timing/status observations. It must not perform
per-track level analysis, compression, filesystem operations, memory probes,
UI publication, RPC, or journal serialization. The current `InputBuffer.put`
path includes work such as memory checks and forwarding; move that work out
of the capture callback when implementing this design.

Accumulate arbitrary driver blocks into processing batches downstream.
`processing_batch_seconds` bounds each drain in source frames and the wait for
an incomplete detector window. A drain takes available data without waiting
for the batch to fill. `silence_window_seconds` independently defines the
detector grid, so changing the batch bound does not change ordinary detection
decisions. Qualify the stated initial defaults on the Pi before deployment;
do not mistake them for measured optima or hardware callback requests.

Emit a partially filled batch on stop, disconnection, or the maximum wait.
Deliver every available frame to the silence decision in order across tiny
blocks and irregular sizes. Define detector windows and timeouts in sample
frames independently of batch boundaries; changing batching must not change
which audio is retained. Preserve activity and uncertainty boundaries within
batches. Routine meter and UI reports can be coalesced independently; capture
lifecycle events cannot be discarded.

Capacity must be measured in frames and bytes, not a queue length inferred
from the first callback size. The current queue chooses its object count from
that first size, so variable blocks do not provide a stable audio-duration
capacity. A frame-capacity buffer must have explicit producer/consumer
ownership: do not overwrite unread frames, wait for free capacity in the
callback, or use an unreviewed Python lock-free ring.

First measure callback, enqueue, batching, silence detection, and writing costs
separately. If Python callback/queue overhead itself cannot handle the observed driver
patterns, a preallocated native frame buffer or stronger capture isolation is
the next implementation decision. Prove its ownership and overflow behavior
before adopting it. Adding another Python thread does not by itself establish
capture isolation or remove GIL contention.

## Frames and clocks

Use integer source-frame positions as the authority for order and adjacency
within a running device stream. Keep wall-clock/ADC timing observations as
observations with their provenance and uncertainty. Callback arrival time is
not a sample boundary detector.

Distinguish these cases explicitly:

- Contiguous delivered frames with timestamp variation: preserve their order
  through silence detection and record timing uncertainty. Do not split an
  active performance or activate silent tracks solely because timestamps jump.
- Known application-buffer loss: advance the source timeline by the exact
  dropped count and record its reason. Keep surrounding audio.
- PortAudio overflow with an unknown lost-frame count: preserve the overflow
  observation and an unresolved clock discontinuity. Do not claim the simple
  delivered-frame counter includes samples the backend never delivered, or
  invent an exact gap duration from callback wall-clock differences.
- Device restart: start a new capture clock and retain evidence for subsequent
  alignment. Cross-device alignment is separate from source-frame continuity.

Reuse existing audio spans, gaps, capture identities, and clock observations
where they express the evidence accurately. Inspect uFor's current treatment
of unknown-duration discontinuities before implementing any schema change;
do not silently label unknown loss as sample-exact continuity.

## Overload policy and diagnosis

No finite buffer guarantees preservation during an indefinitely stalled disk.
The processing path must sustain the incoming rate, and the writers must
sustain all selected tracks active simultaneously, with measured headroom.
Size buffering for measured stalls and an explicit memory budget. Increasing
it only postpones sustained overload.

Prefer dropping or delaying optional analysis, meters, previews, and derived
exports before sacrificing retained audio. Silence detection is essential
capture work, not optional analysis to disable globally under load. If a
decision cannot be made reliably, retain affected undecided material and mark
the uncertainty. This is a temporary conservative response, not a new default
to archive every silent channel. If capture cannot continue, emit a prominent
failure and durable loss evidence; do not silently delete a fragment or
overwrite buffered material. Preserve already written audio.

Collect aggregated callback-size distributions, incoming and persisted frame
counts, confidently suppressed frame counts, queued frames/bytes, oldest-buffer
age, write/flush latency, and exact application drop counts. Keep PortAudio
overflow observations separate from silence suppression.
Measure CPU, memory, and storage on the Pi. Do not publish one diagnostic or
repeat the entire file history on every callback.

## Implementation order

1. Restore unspecified hardware block size and provide an explicit frame-count
   override. This step is already implemented.
2. Specify and test silence, activity, and uncertainty decisions per track,
   including bounded preroll, pending quiet, padding, and short-file retention.
   Implemented for the existing peak-to-peak metric with fixed sample windows.
3. Measure the Pi's callback, detector, and writing throughput. Implement
   frame-based buffering and downstream batching with explicit partial-batch
   draining and loss accounting; keep detector behavior independent of batch
   sizes. The frame buffering, batching, partial-window handling, and recovery
   regressions are implemented; Pi measurements and further isolation are open.
4. Update capture, lifecycle evidence, readers, and documentation together to
   preserve uncertain material while suppressing established silence. Keep
   `record_everything` opt-in and avoid parallel capture implementations.
5. Qualify the complete system on the actual show setup before deployment.

## Verification and acceptance

Use 48 kHz WAV sample regressions of at least one second. Feed identical audio
through one-frame, odd, irregular, and large driver blocks. Retained samples,
suppressed ranges, and native spans must be identical independent of
partitioning and timestamp jitter, including backward/forward clock
adjustments. Test partial-batch stop, rotation, device loss, and retention of
ambiguous low-level or short material.

Test long confidently silent inputs with bounded memory and no audio files,
continuous activity producing one logical performance, quiet around the
padding/timeout boundaries, and activity resuming during pending quiet. Test
uncertainty onset and recovery without indefinite recording of silent inputs.
Test independent tracks with 10 of 18 and 20 of 28 channels silent: silent
tracks must remain suppressed while active tracks remain continuous. Also
verify that explicit `record_everything` and linked recording retain their
documented opt-in behavior.

Exercise queue saturation and stalled writes deterministically. Assert exact
known-loss ranges, unknown-loss evidence, no overwritten or duplicated audio,
preservation of already written data, and correct creation/finish/discard
reporting. Test that optional consumers can stall without blocking essential
capture and silence decisions.

Automated functional tests cannot certify real-time throughput. Run at least a
four-hour qualification on the Pi with X18 and FLOW 8, the show's selected
channels, native MIDI/OSC activity, the actual storage, and representative
monitoring load. Include both the show's silent-channel distribution and all
selected tracks active. Compare PCM and FLAC separately. Include controlled
competing I/O and deliberately irregular callbacks in a separate synthetic
qualification. Keep test revision, settings, diagnostics, and frame accounting.

Accept a configuration only when queue age stays bounded and recovers from
bursts, application drops and PortAudio overflow counts remain zero under the
declared workload, shutdown completes pending silence decisions and drains
retained samples, and every delivered frame is accounted for as retained or
confidently suppressed. Uncertain delivered material must be retained, and
unrecoverable loss must be reported separately. A faster desktop test suite is
not equivalent evidence.

## Additional work beyond the prompt

None. The architecture and qualification work above are proposals for later
implementation; this task does not run hardware capture or change deployment.
