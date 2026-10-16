# Live audio forwarding

recs can forward continuous input PCM to local consumers without opening the
hardware a second time. Enable it at recorder startup with `--forward-audio`
(configuration address `general.forward_audio`). It is disabled by default and
is not a mutable runtime setting. Nothing automatically starts a broadcast.

The tap precedes silence filtering and disk writing. Quiet input is forwarded;
file flushes, session rollover, and disk recovery overlap do not replay audio to
consumers. Forwarding and recording health are separate. Forwarding can continue
while disk writing is suspended, provided the capture is still running.

## Control API

Use the existing public RPC endpoint and instance selection described in
[recs protocol](recs_protocol.md). These commands are advertised by `capabilities`:

| Command | Parameters | Result |
| --- | --- | --- |
| `subscribe_audio` | `source`: exact source key; `channels`: ordered list of one or two distinct one-based physical channels | `{"type": "audio_subscribed", "instance": {...}, "subscription": {...}}` |
| `unsubscribe_audio` | `source`, `subscription_id` | `{"type": "audio_unsubscribed", "stopped": true/false}` |
| `audio_status` | None | `{"type": "audio_status_result", "enabled": bool, "paused": bool, "sources": [...]}` |

Subscription does not open a device, change tracks, or unmute anything. The
source must already be delivering audio. A physical channel need not be a saved
recording track; requesting it is an explicit permission to hear that channel.
The initial implementation supports one subscriber per source, eight active or
pending subscriptions per recorder, and native sample rates up to 192 kHz.
There is no mixing, resampling, file-source forwarding, or automatic source choice.

`subscription` contains `subscription_id`, `source`, `clock_id`, `instance_token`,
`host` (always `127.0.0.1`), `port`, `sample_rate`, `channels`, `sample_format`
(always `f32le`), `version` (1), `generation`, `expires_at`, and `secret`.
Connect within five seconds. `expires_at` uses the local machine's monotonic
clock, not a Unix timestamp. The secret is a signed, single-use capability for
that exact instance, capture, selection, and generation. It is not the capture's
signing key. Do not log the reply, put it on a command line, or save it to disk.

Errors use the existing RPC error shape and `rpc.Client.call()` raises
`ConnectionError`. Busy, paused, muted, unavailable, invalid-channel, expired,
and resource-limited conditions must not be treated as successful subscriptions.
Unknown/already-removed subscription IDs return `stopped: false`; cancellation
never stops recording or a different subscription. A new capture requires a new
negotiation and clock ID. Session/track naming changes do not.

`audio_status` never contains the secret or signing key. Per-source status
includes state, selected channels/subscription ID, clock, sample rate, approximate
sent/dropped frame counts, retained mailbox bytes, last-send monotonic nanoseconds,
last forwarding error, `recording_enabled`, and `muted`. `recording_enabled`
describes the runtime writing gate, not a guarantee that bytes are durable on disk.
Display disk/recording errors alongside it. Health counters are sampled across
processes, not an atomic recording journal.

## Python data client

`recs.base.audio_stream` imports no recorder, device, GUI, or sounddevice code.
After obtaining the control reply, use:

```python
from recs.base.audio_stream import AudioClient, AudioSubscription

subscription = AudioSubscription.model_validate(reply['subscription'])
with AudioClient(subscription) as audio:
    while True:
        header, pcm = audio.receive()
        # pcm is interleaved float32 little-endian in subscription.channels order.
        # Feed it at subscription.sample_rate, not an assumed 48000 Hz.
```

The client closes on incomplete, invalid, stale, or timed-out reads. EOF means
the subscription ended; partial frames must never be reused for a new connection.
Consumers own reconnection, broadcast continuity, resampling, and encoder queues.
Do not let an encoder prevent the consumer from keeping up with live input.

## Wire version 1

Each packet has two unsigned big-endian 32-bit lengths (UTF-8 JSON header bytes,
PCM payload bytes), followed by the header and payload. Headers are limited to
4096 bytes and payloads to 262144 bytes, checked before reading/allocating them.
JSON is metadata only; samples are binary, never base64 or pickle.

The first client header is `{"type": "hello", "subscription": {...}}`, with no
payload. The server replies `{"type": "ready", "clock_id": "..."}`, with no
payload, or closes the connection. Neither side changes the negotiated format.
Unknown/default header fields are handled by the provided Pydantic models;
fields equal to model defaults may be omitted on the wire.

Audio headers have `type: "audio"`, `clock_id`, zero-based packet `sequence`,
`start_frame`, `frames`, capture `timestamp` in wall-clock seconds, `offered_at`
in local monotonic seconds, and optional `input_status`. Payload length must be
`frames * len(channels) * 4`. Packets contain at most about 20 ms of audio.

Frame intervals are half-open and source/capture relative, matching recording
ingress, not file offsets. Sequence numbers count delivered packets. A jump in
`start_frame` after the preceding packet's end indicates a known gap; the first
packet simply begins at the live edge. `input_status` can report PortAudio
overflow with unknown loss length. Do not invent an exact duration or infer
cross-device clock synchronization. Subscription termination is EOF; query
`audio_status` to distinguish pause/mute, stopped capture, and forwarding errors.

## Privacy, failure isolation, and limits

- Pause closes forwarding and capture. Configured machine mic mute excludes the
  source and rejects subscriptions. While connected, the forwarding worker also
  checks the saved machine mute about every 200 ms, including when audio is idle.
  A newly saved mute or unreadable/malformed mute configuration closes forwarding
  without requiring a recorder configuration reload. This does not add live
  reconfiguration of recording itself. Consumers must flush their own buffers on
  EOF and retain their own broadcast mute. Already-sent audio cannot be recalled.
- Only loopback TCP is exposed. Capability delivery uses the existing local
  control channel, not the private GUI protocol. On POSIX, subscription requires
  that the control socket and its directory belong to the current user and are
  not writable by other users. Windows uses the existing named-pipe control
  security. Administrative/same-user processes are trusted, not isolated by this
  feature. Cross-platform ACL and physical-device acceptance still need testing
  on their actual target systems.
- Capture offers an existing owned array reference with a non-waiting mailbox
  lock. No network, JSON, channel conversion, or extra full input-array copy is
  performed in the callback. The worker converts only the requested channels.
  With no subscription there is no retained forwarding audio or PCM conversion;
  an enabled source still has an idle worker/listener and capture-progress counters.
- The mailbox is limited to 100 ms, 1 MiB of native input arrays, and 128 blocks.
  Oversize callback blocks are dropped rather than increasing the budget;
  negotiation rejects an already-observed oversize block configuration. Keep
  recording's buffer independent. Under its existing memory-reserve policy,
  neither path retains a new block.
- The worker may additionally hold one in-flight native block, selected PCM, and
  one wire packet. At the maximum supported rate/channels this is less than
  about 2.5 MiB of forwarding-owned audio per subscriber, excluding object and OS
  overhead. Eight subscriptions bound this to about 20 MiB. Requested socket
  buffers are 64 KiB send and 4 KiB receive; the OS can adjust those sizes.
- Old complete unsent blocks are discarded, not accumulated. Sending has a total
  deadline of 250 ms from mailbox offer. A failed/partial send closes that
  subscriber, not recording. The client also rejects packets older than 250 ms,
  including bytes that spent too long in kernel buffers. The target is not a
  hard-real-time or end-to-end broadcast latency guarantee.
- Handshakes have a 200 ms read deadline and are rate-limited to 20 attempts per
  second per source. Setup/allocation/worker failures disable forwarding only.
  A failed worker is reported in status; it is not silently restarted by opening
  another hardware stream. Shutdown abandons stale audio, closes sockets, and
  uses a bounded worker join. Actual capture stalls and clock failures remain
  detectable, including while disk writing is suspended.

streamO integration and its agreed silence/reconnect/outage policy are not yet
implemented here. See [remaining work](../plan/audio-forwarding.md). No service
deployment or hardware validation is implied by the automated tests.
