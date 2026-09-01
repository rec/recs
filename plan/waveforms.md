# Live Waveforms

## Goal

Provide an optional live waveform stream for every configured mono or stereo
audio track while Recs is running. Recs reduces captured audio to compact
min/max envelopes and sends those envelopes through the public Reccy event
protocol. A client draws and scrolls the waveforms.

This feature does not create SVGs, images, waveform cache files, edit files, or
record entries. It does not process existing recordings. Existing tools are
better suited to generating waveforms from completed audio files.

Waveform streaming is inactive until the public control client subscribes. Recs
supports one waveform consumer, so the implementation does not need independent
subscriptions, histories, or delivery rates for multiple clients.

## Responsibilities

Recs is responsible for:

- preserving configured mono and stereo track grouping;
- reducing live audio to fixed-duration min/max buckets;
- attaching source-frame and capture-time positions to those buckets;
- publishing bounded batches without delaying audio capture or recording;
- reporting gaps when waveform data has been dropped;
- stopping waveform work when the client unsubscribes.

The client is responsible for:

- retaining only the history needed for its visible window;
- choosing colors, vertical scales, labels, and viewport duration;
- drawing one lane for mono and two lanes for stereo;
- advancing the viewport at display refresh rate;
- handling layout changes, sequence gaps, disconnects, and reconnects.

Recs does not send an image for the client to redisplay and does not maintain a
scroll position. Scrolling is presentation state and belongs to the client.

## Track Identity

A waveform represents one configured Recs track:

- A mono track has one channel and one envelope lane.
- A stereo track has two channels and two envelope lanes.
- Channel order in a stereo track is preserved.

Recs must not infer stereo pairs from odd/even hardware channel numbers or from
adjacent logical channels. A configured stereo track on hardware channels 2-3
is one stereo waveform. Separate mono tracks on channels 2 and 3 are two mono
waveforms.

The stable track identity is the source key plus its ordered channel numbers.
The current track name is display metadata and may change without changing the
identity. Track order follows the current configured order for that source.

Waveforms show live captured input before silence filtering, file segmentation,
or encoding. They continue to show input while recording is paused or while a
track is below its recording threshold. This makes them signal monitors rather
than pictures of whichever samples currently happen to be written to files.

## Subscription Protocol

Add these public Reccy control commands:

```json
{"type":"request","command":"subscribe_waveforms","params":{}}
{"type":"request","command":"unsubscribe_waveforms","params":{}}
```

Both return the current subscription state:

```json
{
  "type": "waveform_subscription",
  "active": true,
  "bucket_milliseconds": 20,
  "batch_milliseconds": 100
}
```

Subscription is transient and receives no historical waveform data. The client
starts the public event connection before subscribing, explicitly unsubscribes
when finished, and then closes its event connection.

The daemon propagates subscription changes to every active source process. A
source discovered after subscription starts receives the active state when it
is created. The acknowledgement means the request has been accepted; individual
sources may begin sending after their control messages arrive.

Do not add waveforms to `rows`, `status_snapshot`, or the daemon status JSON
file. Those are snapshots and would either retain large arrays or poll them at
unsuitable rates. Layouts and batches are `waveform_layout` and `waveform`
events on the public Reccy event connection.

## Layout Messages

On subscription, source startup, and every track reconfiguration, send a
`waveform_layout` event before sending batches for that layout. Its `data`
object is:

```json
{
  "source": "X18: USB Audio (hw:0,0)",
  "generation": 3,
  "sample_rate": 48000,
  "bucket_frames": 960,
  "tracks": [
    {"channels": [1], "name": "Vocal"},
    {"channels": [2, 3], "name": "Keys"}
  ]
}
```

`generation` increases whenever a source's track layout changes or its live
waveform stream restarts. A client discards retained data for an older
generation. Source keys and ordered channel numbers identify tracks; names are
labels only.

If a source goes offline, the ordinary device status still reports that fact.
No fabricated zero-amplitude buckets are sent. The missing time appears as a
gap until the source returns with a new generation.

## Waveform Batches

Configure the envelope bucket and network batch durations with
`waveform_bucket_milliseconds` and `waveform_batch_milliseconds`. They default
to 20 ms and 100 ms. The batch duration must be an exact multiple of the bucket
duration. The defaults give 50 horizontal samples per second and group five
buckets into each of at most ten waveform messages per source per second.

A `waveform` event's `data` object has one timeline shared by every configured
track on that source:

```json
{
  "source": "X18: USB Audio (hw:0,0)",
  "generation": 3,
  "sequence": 42,
  "sample_rate": 48000,
  "bucket_frames": 960,
  "start_frame": 196800,
  "start_timestamp": 1788000004.1,
  "present": [true, true, true, true, true],
  "tracks": [
    {
      "channels": [1],
      "minimum": [[-0.12, -0.18, -0.09, -0.04, -0.14]],
      "maximum": [[0.10, 0.16, 0.08, 0.05, 0.13]]
    },
    {
      "channels": [2, 3],
      "minimum": [
        [-0.22, -0.19, -0.25, -0.20, -0.21],
        [-0.20, -0.18, -0.23, -0.19, -0.20]
      ],
      "maximum": [
        [0.21, 0.18, 0.24, 0.19, 0.20],
        [0.19, 0.17, 0.22, 0.18, 0.19]
      ]
    }
  ],
  "dropped_batches": 0
}
```

The outer `minimum` and `maximum` lists follow the track's channel order. Their
inner lists follow the five bucket positions. Amplitudes are floating-point
values normalized to digital full scale. Preserve values outside `[-1, 1]` so
the client can show clipping rather than receiving silently clipped display
data.

Source frames are authoritative for bucket continuity. `start_timestamp` maps
the first bucket to wall-clock time for alignment and labeling. Every complete
bucket spans exactly `bucket_frames`; the source process derives
`bucket_frames` by rounding the configured bucket duration at that source's
sample rate.

`present` distinguishes captured digital silence from unavailable waveform
data. A bucket touched by a known processing drop or source-frame discontinuity
is marked false. Its extrema are encoded as zero placeholders and must not be
drawn as silence. PortAudio overflow reports remain ordinary errors because
PortAudio does not provide enough missing-frame information to position an
exact gap.

`sequence` increases for every batch produced by one source generation. A
sequence discontinuity or positive `dropped_batches` tells the client to leave
a gap and continue with the newest data. Live display should favor current data
instead of accumulating latency.

## Audio-Process Reduction

Perform envelope reduction in each `SourceRecorder` process, where
`_receive_update()` already has one `Block` per configured `ChannelWriter`.
Collect the waveform after converting the input array to each configured track
but before `should_record()`, silence filtering, or file writing.

Align bucket boundaries to absolute source frames, not callback or audio-block
boundaries:

```text
bucket N = [N * bucket_frames, (N + 1) * bucket_frames)
```

An input block may complete several buckets or only part of one. Retain only
one partial bucket per track between input blocks. Use NumPy reductions over
contiguous slices; do not iterate over individual audio frames in Python.

When unsubscribed, no envelope arrays are allocated and no min/max reductions
run. When subscribed, memory remains bounded by one partial bucket plus five
completed buckets per channel. CPU cost is one min/max reduction over the audio
already being processed. Raw audio never crosses the source-process boundary.

Add the active waveform state to `SourceControl`. Add an optional bounded
waveform batch list to `SourceUpdate`. Track reconfiguration discards partial
buckets, increments the generation, and sends a new layout before new batches.

## Bounded Transport

Waveform display must never backpressure audio capture, file writing, or the
recorder's main loop.

`SourceUpdateTransport` currently coalesces pending source updates. Extend its
merge behavior to preserve waveform batches in order up to a fixed limit of
five batches per source, representing five configured batch intervals (500 ms
by default). When the limit is exceeded, discard the oldest batches and
increment `dropped_batches` on the next retained batch.

The public RPC server owns a separate asynchronous bounded waveform queue. It
must preserve layout-before-data ordering and hold no more than five batches
per source. If the client cannot keep up, discard the oldest waveform batches,
update the drop count, and send the newest data. Never wait for the client from
an audio or recorder thread.

There is only one waveform client, but all subscription and queue state remains
protected by the public server's existing lock. Unsubscribing clears the queue
and propagates disabled waveform state to the recorder and source processes.

## Smooth Client Scrolling

The client keeps a bounded ring buffer for each track and generation. A useful
default is the visible duration plus one batch on either side; the exact
visible duration is client presentation policy.

The client must not move the viewport only when a network batch arrives (every
100 ms by default).
It advances the time axis from its own monotonic clock on every display frame,
normally through `requestAnimationFrame` for a web client. Each incoming batch
adds envelope data at its source-frame position. This separates the 10 Hz data
delivery cadence from a 60 Hz or higher visual animation cadence.

Anchor the newest complete bucket near the right edge and use elapsed client
monotonic time to advance between batches. Correct small timing differences
gradually when a new batch arrives; reset immediately after a generation change
or a large sequence gap. The waveform geometry may be drawn with Canvas or
another retained client-side renderer. Repeatedly reparsing or replacing an
SVG document is not part of this design.

At the default 20 ms per bucket, a 20-second viewport contains 1,000 envelope
columns per channel. The client may combine adjacent buckets when displaying a
longer window, but it must combine them by taking the minimum of minima and
maximum of maxima so peaks are not lost.

## Architecture

```text
recs/audio/live_waveform.py   Frame-aligned bounded min/max reduction
recs/ui/source_recorder.py    Enable reduction and carry source batches
recs/ui/source_process.py     Propagate subscription control
recs/ui/device_lifecycle.py   Forward layouts and batches to the display
recs/daemon/gui_protocol.py   Public subscription request and response classes
recs/daemon/external_ipc.py   Subscription state and bounded public events
```

`live_waveform.py` contains no protocol or GUI code. It accepts track blocks and
source-frame ranges and returns complete envelope batches. `gui_protocol.py`
defines the public subscription request and response. `external_ipc.py` owns
the transient subscription and delivery queue. The displaying application owns
its visible ring buffers.

No new dependency is required.

## Failure Behavior

- An invalid subscription request receives the ordinary protocol error and does
  not enable waveform processing.
- A waveform reduction or serialization error disables waveform streaming and
  reports one Recs error without stopping recording.
- A slow client causes old waveform batches to be dropped, never audio frames.
- A disconnected event client loses its transient waveform history; it must
  reconnect before consuming more events.
- A source failure ends its batches. A restarted source uses a new generation.
- Non-finite input extrema are represented as a waveform-stream error rather
  than serialized as invalid JSON.

## Tests

Use 48 kHz WAV regression fixtures of at least one second for tests that process
digital audio.

1. Parse and serialize public subscribe, unsubscribe, subscription, layout,
   and batch messages, including the Recs payload version change.
2. Verify that a new client is unsubscribed and that no source process performs
   reductions before subscription.
3. Reduce one second of mono audio into buckets of the configured duration and
   compare minima and maxima with regression data.
4. Reduce a stereo track and verify channel order and separate extrema.
5. Configure one stereo track on channels 2-3 and verify one track entry;
   configure channels 2 and 3 as mono tracks and verify two entries.
6. Feed audio blocks that split bucket boundaries and verify absolute
   source-frame alignment without duplicate or missing samples.
7. Verify that digital silence is present, while a processing drop or frame
   discontinuity produces an absent bucket.
8. Verify that waveform input is collected before silence filtering and remains
   available while recording is paused.
9. Reconfigure tracks and verify that partial buckets are discarded, the
   generation changes, and the new layout precedes its data.
10. Merge pending source updates and verify ordered batches, the five-batch
    limit, drop counts, and preservation of ordinary source status.
11. Stall a fake public event connection and verify bounded delivery, newest-data
    preference, sequence gaps, and no blocked recorder thread.
12. Unsubscribe and verify that queued waveform data is cleared and every
    source process stops reducing audio.
13. Exercise 18 mono channels and nine stereo pairs at 48 kHz and verify fixed
    memory use, ten batches per second per source, and no raw-audio transport.
14. Manually display a 20-second scrolling window for mono, stereo 2-3, silence,
    clipping, a dropped batch, reconfiguration, and source restart. Confirm that
    scrolling remains smooth while batches arrive at 10 Hz.

## Implementation Order

1. Add public subscription commands and waveform event data classes with
   serialization tests.
2. Implement and regression-test the frame-aligned bounded envelope reducer.
3. Add source-process subscription control, track-layout generations, and
   optional waveform data to the bounded source-update transport.
4. Forward waveform data through device lifecycle and add the public RPC
   server's separate bounded waveform delivery queue.
5. Disable and clear waveform processing on unsubscribe, source restart, and
   protocol failure.
6. Expose bounded waveform delivery through public Reccy events and add
   end-to-end fake-client tests for cadence, ordering, drops, and
   reconfiguration.
7. Run the full Recs verification sequence, then manually verify CPU use,
   recording stability, and smooth client rendering with the target hardware.

## Additional work beyond the prompt

None.
