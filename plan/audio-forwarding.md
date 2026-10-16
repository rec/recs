# Audio forwarding: remaining work

The recs implementation and client are documented in
[live audio forwarding](../doc/audio-forwarding.md). The capture tap, opt-in
configuration, local subscription API, authenticated binary PCM, bounded queues,
privacy controls, status, and failure-isolation regressions are implemented.
This plan contains only the remaining integration and acceptance work.

## Agreed policies

- Local mono/stereo forwarding from an existing hardware capture; explicit source
  and ordered channels; one subscriber per source in the first implementation.
- Continuous input, including quiet passages, not file/silence-filtered audio.
- Explicit recording pause and machine mic mute stop forwarding. streamO retains
  its independent broadcast mute and must purge buffered audio on termination.
- Storage failure/replacement alone does not stop a still-working live capture.
- Authenticated loopback binary PCM, with negotiation on the existing control API.
- Unexpected input loss: streamO sends timed silence and retries for 30 seconds,
  then stops the broadcast with a clear error. Intentional pause/mute stays silent
  until explicitly resumed. Never fall back automatically to opening hardware.
- Recording takes priority over forwarding. Latency targets are measured goals,
  not zero-drop or hard-real-time guarantees.

## 1. streamO adapter, in its own repository

Implementation needs a separately scoped request for streamO. No streamO files
or running services are changed by the recs implementation.

- Add an explicit recs-input mode mutually exclusive with device capture.
  Select the exact instance, source key, and physical stereo pair. Do not guess,
  downmix, start another device, or alter recording tracks.
- Negotiate through the recs public control endpoint and use the provided
  `recs.base.audio_stream.AudioClient`, rather than copying its parser.
- Reuse streamO's encoder feeding, gain/mute, and health handling. Match FFmpeg's
  declared input sample rate and channel count to negotiation; keep output
  resampling, encoding, credentials, and network delivery in streamO.
- Preflight checks recs availability, permissions, and source selection without
  opening or probing the hardware. Do not consume a single-use capability during
  preflight and try to reuse it for live operation.
- Handle EOF, frame gaps, stale data, new capture clocks/formats, and encoder
  stalls without backpressuring recs. Flush all old PCM on reconnect and encoder
  replacement; never concatenate a partial old frame with a new stream.
- Use `audio_status` to distinguish intentional pause/mute from unexpected loss.
  Implement the agreed silence/reconnect/30-second timeout policy with visible
  degraded health. Do not treat indefinite silence as a healthy broadcast.
- Test these policies with fake time and transports, then update streamO input,
  configuration, preflight, and operator documentation.

## 2. Physical and performance acceptance

- Run sustained recs-to-consumer and then recs-to-streamO tests on the X18 and
  available Windows/macOS/Linux hosts, including microphone and control ACL
  checks. Automated spawn tests do not prove native device or platform security.
- Measure capture-to-consumer latency, callback overhead, CPU, idle-worker cost,
  memory, and device block duration on the real machine. The initial targets are
  about 100 ms of application buffering and under 250 ms capture-to-consumer
  latency, excluding encoder/broadcast latency. Retune bounds only from evidence.
- Verify simultaneous recording and forwarding during consumer restart, slow
  encoder, device unplug/replug, bad discovery snapshots, pause/mute, storage
  suspension/replacement, and disk recovery. Check saved audio and stream frame
  intervals for unintended gaps, duplication, and recovery overlap replay.
- Verify bounded shutdown/SIGINT and no retained audio or stuck forwarding worker
  after capture ends. Check the UI reports recording and forwarding separately.
- Do not deploy to or restart the show machine without a separate request.

## Deferred, not required for the first consumer

Independent multi-consumer fan-out, mixing/resampling in recs, synchronized
multi-device output, remote clients, file playback, historical replay, shared-memory
rings, and a standalone forwarding package remain outside this plan.

## Additional work beyond the prompt

None. The current implementation request covers recs only; streamO integration,
physical acceptance, and deployment require their own scope/authorization.
