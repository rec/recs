# Near-real-time audio forwarding

Status: proposal, not implemented. Implementation requires approval of the
architecture and recommended policies below. This document does not authorize
changes to streamO, reccy, running services, or show-machine configuration.

## Goal and boundaries

Allow a local consumer such as streamO to receive selected audio from recs'
existing capture, without opening the audio device a second time. Recording is
the priority: a missing, slow, broken, or restarting consumer must not make
recording wait, lose audio, restart capture, or fail shutdown.

Forward continuous live input, including quiet passages, rather than audio
selected for file writing. Do not tail WAV/FLAC files, replay recovery overlap,
or delay forwarding until a recording file closes or flushes.

recs owns capture, channel selection, timestamps, and local delivery. streamO
owns broadcast mute/gain, resampling, encoding, pictures, destination credentials,
and network delivery. dvice continues to own device discovery and recovery
support; this does not move audio-device ownership into streamO.

First slice: one already-selected hardware source and one ordered mono/stereo
channel selection per subscription, on the same machine. Multiple sources can
be subscribed independently later, but recs does not align, mix, or resample
independent device clocks. File playback, remote subscriptions, historical
replay, general routing, and a new standalone package are outside this plan.

## Current integration points

- `recs/cfg/device.py`: the device callback copies the native input array once
  and passes an `Update` to `InputBuffer.put`.
- `recs/runtime/input_buffer.py`: assigns source frame intervals before
  recording-queue admission. Its timeline includes known queue-dropped frames.
- `recs/runtime/source_recorder.py`: processes the queue, applies track/silence
  decisions, and writes files. It currently stops consuming that queue while
  writing is suspended. Tapping this loop would inherit disk backlog and
  suspension, so it is not the proposed live tap.
- `recs/runtime/source_transport.py`: merges/coalesces status updates. PCM must
  not be added to that transport or to the similarly bounded waveform events.
- `recs/daemon/external_ipc.py`, `instances.py`, and
  `recording_control_protocol.py`: existing control and instance targeting.
  Extend these for negotiation, not bulk audio.
- streamO's `streamo/audio.py` currently opens its own sounddevice input,
  selects a stereo pair, and feeds PCM to FFmpeg. Its
  `streamo/composition.py` already declares float32 little-endian stereo PCM on
  FFmpeg stdin. The integration replaces capture in this mode, not its output
  pipeline. No streamO files are changed by this plan.

## Architecture

```text
one existing device callback, one owned input copy
    -> InputBuffer frame assignment and existing memory-reserve check
        -> existing bounded recording queue -> analysis/silence filtering/files
        -> optional bounded reference mailbox -> forwarding worker
            -> dedicated local binary connection -> consumer -> encoder/broadcast

existing recs control RPC -> authorize/select/negotiate/stop subscription
```

Add the tap at capture ingress, after assigning the frame interval and applying
the memory-reserve policy, before recording-queue admission. Keep its frame and
timestamp metadata identical to the recording ingress. Recording queue pressure
must not itself force a forwarding gap, or vice versa; both still yield to the
existing global memory-reserve policy.

The callback may only offer the already-owned block and small metadata to a
bounded mailbox. No socket operations, channel conversion, JSON serialization,
logging, encoder work, waiting for queue space, or subscriber callbacks there.
Any synchronization must have a non-waiting offer path; contention drops the
forwarding offer rather than waiting on the sender. This is bounded best-effort
Python work, not a hard-real-time guarantee.

The worker lives in the existing source process, separate from its disk-writing
loop. It selects channels, normalizes PCM, frames messages, and services bounded
subscriber state. Do not relay PCM through the parent recorder process. Use
ordinary worker threads and standard-library primitives initially, not async,
shared-memory rings, an extra capture process, or an audio-server dependency.

Retain references to the existing callback-owned arrays, not additional full
device-block copies. Treat those arrays as immutable across both branches and
verify that assumption against every writer path before implementation. Channel
selection, dtype conversion, and wire serialization may require copies in the
worker; this is not an end-to-end zero-copy design. No subscriptions means no
mailbox retention, conversion, sender, or extra audio copy.

## Proposed control and data contract

Use the existing instance selector and serialized control operations. Proposed
commands are `subscribe_audio`, `unsubscribe_audio`, and `audio_status`, exposed
through capabilities. Names and exact schemas become public only when the first
implementation is reviewed.

A subscription identifies the selected recs instance, exact source key, and
ordered physical channel numbers, using recs' existing one-based convention.
Names/aliases are display metadata, not identity. The first streamO adapter
requests an explicit stereo pair; no automatic downmix or guessed source.
Reject duplicate, unavailable, muted, out-of-range, or unsupported selections
with an actionable error. Do not start capture or change recording tracks merely
because a consumer subscribes. Forwarding access is an explicit opt-in permission
to hear the requested physical channels, including channels not written as tracks.

Recommended transport: a separate length-framed binary TCP connection bound only
to `127.0.0.1`, with an OS-assigned port. This gives one local data transport on
Windows, macOS, and Linux, independent of control RPC's platform-specific
transport. Reuse existing reccy lifecycle/endpoint facilities where they fit;
inspect them before implementing, rather than adding a competing service registry.
Do not generalize reccy or introduce a dependency for this feature.

Control negotiation returns a subscription ID, protocol version, endpoint,
short-lived single-use connection secret, recs instance identity, capture clock
ID, source key, sample rate, channel order, and sample format. Deliver the secret
only over the existing user-restricted control channel, never in logs, ordinary
status, or command-line arguments. Loopback alone is not authentication. Limit
pending handshakes and expire unused negotiations; verify the existing control
endpoint permissions on all three platforms before treating this as private audio.

Each data connection has one subscriber and one selection. Start with a versioned
descriptor, then bounded length-prefixed messages: audio, discontinuity, source
state, and end. Define header byte order and maximum message/header lengths in
the protocol specification before writing client code. Do not use pickle, JSON
sample arrays, or base64 PCM. Reject invalid lengths before allocating payloads.

Audio carries sequence number, capture clock ID, start frame, frame count,
capture timestamp, and interleaved `f32le` payload in negotiated channel order.
Integer capture is normalized in the worker using the existing sample scaling
semantics. The source's native sample rate is authoritative; do not label audio
48 kHz merely because the consumer expects it. Bound message duration, splitting
large callback blocks off the callback thread when necessary.

Frame intervals are half-open and belong to one capture clock, not a filename or
session. Session rollover and disk failover do not reset that clock or replay
overlap. A real capture restart creates a new clock and requires renegotiation.
Known dropped blocks produce exact gap intervals. PortAudio overflow may have
unknown loss length: report it as such, without inventing sample-exact continuity.
Never infer device synchronization from similar wall-clock timestamps.

## Bounded latency and failure behavior

Initial engineering targets, to measure rather than promise: about 100 ms of
application buffering and under 250 ms capture-to-consumer latency on a healthy
local machine, excluding the encoder and broadcast service. Account for device
block duration, retained full-device arrays, worker conversion, per-client queues,
partial sends, kernel buffers, and consumer buffering. A block larger than the
budget must not silently enlarge the budget.

Bound queued frames, bytes, age, connections, and pending handshakes. Start with
one subscriber per source; do not advertise fan-out until independent per-client
budgets and a recorder-wide memory cap are implemented and tested. Choose concrete
limits from measurements in slice 1, and reject requests that exceed them before
allocating buffers. Bound forwarding CPU as well, including selection/conversion
for high-channel-count devices. Forwarding yields first under memory pressure.

Prefer fresh audio to an ever-growing backlog. Drop old unsent complete blocks,
record the gap, and resume near the live edge. A partially transmitted frame
cannot be discarded from a TCP byte stream: finish it within the deadline or
close that subscriber connection. If socket buffering makes delivered audio too
old, disconnect rather than sending minutes of catch-up audio. The consumer also
checks frame age and discards stale complete messages.

Consumer stalls, disconnects, malformed handshakes, broken pipes, descriptor
exhaustion, and allocation failures disable or reject forwarding, not recording.
Keep exception containment narrow and outside the callback. Publish coalesced
health/counters with rate-limited warnings; never emit an event for every dropped
block. No retry sleeps or resource growth in the recording loop.

On actual capture failure/stall/restart, end the connection with a reason when
possible, otherwise EOF. The consumer reconnects through control negotiation
with bounded backoff; recs does not keep unbounded reconnect sessions. Discovery
omission/reduced channel reports must not interrupt an already progressing
capture, preserving the lifecycle fix. A genuine format change ends the stream,
rather than silently changing payload interpretation.

Shutdown rejects new negotiations, stops offers, closes sockets to wake blocked
workers, releases retained arrays, and joins with a deadline. Never drain stale
audio before stopping recording. Cover SIGINT, normal shutdown, and child-process
exit; EOF must suffice when an end message cannot be sent.

## Operator and privacy policies recommended for approval

- Forwarding is disabled by default. Subscription itself never unmutes a source
  or opens another hardware stream. Show source/channels/subscriber state clearly.
- Explicit recs pause and machine mic mute stop forwarding too. Purge queued
  audio and close affected subscriptions, including during shutdown. Audio already
  delivered to the consumer/kernel cannot be recalled; streamO must purge its own
  input buffers on pause/end and retain its independent broadcast mute.
- Quiet filtering does not mute forwarding. Operators must not mistake an idle
  file writer for a privacy control.
- Storage failure or replacement alone may leave forwarding active, because the
  capture can still be useful live. Status must separately say whether audio is
  being recorded and forwarded. This policy is distinct from explicit pause/mute
  and requires ingress forwarding to work while the writer loop is suspended.
- A new session or track rename does not interrupt physical-channel subscriptions.
  Capture restart, source identity change, or changed channel availability requires
  a new subscription. Never silently switch devices or channels.
- Do not automatically fall back to streamO opening the hardware device when recs
  disappears. That could compete with recs' recovery and capture unintended input.
  streamO should show degraded input and either send timed silence or stop its
  encoder according to an explicit broadcast policy. Recommend timed silence for
  short outages, with bounded recovery and a visible alert, not an endless hidden
  healthy state.

These are recommendations, not previously agreed behavior. In particular, confirm
pause/mute semantics, continued forwarding during storage failure, the loopback
binary transport, and the streamO outage policy before implementation.

## Implementation slices and acceptance

1. **Capture tap and budgets in recs.** Add the optional ingress mailbox and worker
   lifecycle, without a public transport yet. Prove that quiet audio is continuous,
   retained audio is immutable, frame intervals match capture ingress, recording
   is unchanged, writer suspension does not block forwarding, and slow consumers
   cannot increase capture/recording queue pressure. Measure callback overhead,
   source-loop CPU, memory, and block duration to finalize the limits above.
2. **Local subscription protocol in recs.** Add negotiation, instance targeting,
   channel validation, authenticated binary delivery, bounded partial writes,
   status, discontinuities, teardown, and a small reusable client alongside the
   recs protocol. Keep the client independent of sounddevice and recorder imports.
   Do not copy the parser into each consumer or create a new project preemptively.
3. **streamO adapter, separately authorized in that repository.** Add an explicit
   recs-input mode mutually exclusive with device capture. Reuse streamO's encoder
   feeding, gain/mute, and health handling. Preflight must inspect the recs
   subscription without probing/opening the hardware. Match FFmpeg's declared input
   rate/channels to negotiated PCM, and keep any needed output resampling in
   streamO. Handle EOF, gaps, rate changes, fresh-start reconnect, and encoder stalls
   without backpressuring recs. Its broadcast credentials never pass to recs.
4. **Acceptance and documentation.** Run focused regressions, both repositories'
   suites and checks, then physical Windows/macOS/Linux checks where available.
   Update the recs API/operator docs and streamO input/preflight docs only when
   implemented. Do not deploy to a show machine without separate authorization.

Tests must cover identical recorded output with forwarding absent, active, stalled,
and disconnected; no second device open; channel order and integer scaling;
quiet audio; capture restart and clock changes; missing/reduced discovery;
pause/mute with queued audio; disk-full/failover without replay; memory pressure;
malformed/oversized/unauthenticated messages; fragmented reads and partial writes;
consumer crash; encoder stall; subscription expiry; source exit; and bounded
shutdown. Use deterministic fake transports/clocks for failure tests. Digital-audio
regressions write WAV fixtures at 48 kHz for at least one second; separately test
non-48-kHz negotiation without implying resampling support in recs.

Physical acceptance includes a sustained recs-to-streamO run on the X18, consumer
restart, capture unplug/replug, pause/mute, disk trouble, and measured latency and
resource use. Automated success is not proof of hardware reliability or a
zero-drop guarantee under OS scheduling or resource exhaustion.

## Additional work beyond the prompt

None. This change only adds this plan. No implementation, dependency changes,
service operation, or cross-repository edits are included.
