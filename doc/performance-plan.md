# Raspberry Pi performance plan

## Goal

Build a stage recorder around a Raspberry Pi that records the Behringer X18
reliably while allowing optional control and streaming processes. Local recording
is the primary job. Streaming and control are allowed to fail without affecting
recording.

The expected final workload is:

1. `recs` daemon recording the X18 locally.
2. A separate Twitch streamer capturing only the stereo main mix.
3. A separate stage-control web app for phone or tablet control.

This plan does not include lighting control.

## Hardware target

A Raspberry Pi 5 with Raspberry Pi OS Lite is the preferred final target.

Memory does not appear to require a large Pi:

- 2 GB is feasible for the described Lite OS workload.
- 4 GB is the conservative sweet spot if the price difference is acceptable.
- 16 GB is unnecessary for this design.

The main memory consumers are Python, NumPy, source recorder processes, ffmpeg,
and OS cache. The audio buffer itself is modest. At 18 channels, 48 kHz, and
4-byte in-memory samples:

```text
18 channels * 48,000 samples/sec * 4 bytes * 10 sec = 34.6 MB
```

Even with Python and NumPy overhead, the recorder should fit comfortably in a 2
GB or 4 GB Lite system if no desktop, browser, containers, or heavy GUI stack is
running.

## Storage target

Record locally to a USB flash drive or SSD, not to the SD card.

For 18 channels at 48 kHz, 24-bit uncompressed PCM:

```text
48,000 samples/sec * 18 channels * 3 bytes = 2.59 MB/sec
2.59 MB/sec * 3600 sec = 9.33 GB/hour
```

Approximate show sizes:

```text
2 hours = 18.7 GB
5 hours = 46.7 GB
```

A 64 GB USB drive is enough for one long show if it starts empty, but with limited
margin. A 128 GB drive is a better practical minimum. A 256 GB drive gives more
space and may have better sustained-write behavior, but the larger physical size
can increase the risk of being bumped.

The preferred low-cost mechanical strategy is:

1. Try a reputable nano USB flash drive.
2. Run long full-rate tests in the real case.
3. If heat or stalls appear, use a short USB extension and strain relief.

The important risk is not average bandwidth. The risk is long write stalls from
flash throttling, garbage collection, heat, or a nearly full filesystem.

## Recording format

Use uncompressed 24-bit WAV or RF64 for the primary local recording.

Advantages:

- low CPU use;
- predictable write rate;
- simple recovery after crashes or power loss;
- no compression stalls in the recording path.

FLAC is reasonable for secondary archival workflows, but it adds CPU cost and
has material-dependent compression. The primary stage recording should keep the
write path simple until testing proves otherwise.

For 24-bit files, `recs` can use 32-bit samples in memory and let libsndfile write
`PCM_24`. There is no normal NumPy `int24` dtype.

## Buffering

The current default recorder buffer is:

```text
--audio-buffer-seconds 10
```

At 48 kHz this creates roughly 10 seconds of callback-to-writer buffering per
source recorder. If the disk blocks longer than this, `recs` will start dropping
audio blocks and reporting buffer overflow/drop counters.

This is intended to absorb ordinary write jitter, not unlimited storage stalls.
Long burn-in tests should confirm that the chosen USB drive does not produce
stalls near this duration.

## Twitch streaming

The Twitch streamer should be a completely separate program.

It should open the audio device independently for one stereo main-mix pair, encode
that mix, and stream to Twitch. It should not communicate with `recs` directly.

Reasons:

- Twitch/network failures cannot block local recording.
- The streamer can be restarted independently.
- ffmpeg or encoder crashes do not affect `recs`.
- The streamer can run at lower CPU and I/O priority.

The streamer should use a cheap video source:

- static image;
- pre-rendered low-resolution H.264 loop;
- possibly a long low-resolution pre-rendered animation with keyframe-aligned
  seeks.

Avoid live camera video and live crossfades. They cost more CPU and add failure
modes. The practical Twitch feed is audio-first with simple visual filler.

## Process isolation

Run each function as an independent user service:

```text
recs daemon       high priority, owns local recording
twitch-streamer  low priority, best-effort network stream
stage-control    local web UI and control aggregator
```

Systemd should own process lifecycle. `stage-control` should not directly
supervise or embed the other programs. It should communicate with services through
small local APIs.

If the streamer dies, recording should not notice. If stage-control dies,
recording should not notice.

## Stage control

`stage-control` should expose a small web app over the Pi's private network:

```text
Phone/tablet joins: recs-control
Browser opens:      http://192.168.4.1
```

It should show:

- recording status;
- input/device status;
- disk free space;
- buffer pressure and dropped frames;
- simple per-channel signal indicators;
- Twitch status.

It should provide explicit buttons:

- calibrate noise floor;
- start/stop/restart Twitch stream;
- safe shutdown;
- possibly download or inspect recent manifests.

`stage-control` communicates with `recs` through a local daemon control API,
preferably a Unix domain socket with JSON request/response messages. It should
communicate with the Twitch streamer through the same style of local API.

## Calibration

Calibration should happen after the mixer is set up, not only at boot.

There are two useful control paths:

1. Phone/tablet button in `stage-control`.
2. Dedicated command USB stick as a fallback physical trigger.

The calibration direction is:

- measure each selected channel or stereo pair for 500 ms;
- add `preview_headroom`;
- update per-track `channel_noise_floors`;
- do not change the global `--noise-floor`;
- do not recommend quiet-before or quiet-after values.

Quiet-before and quiet-after are user-chosen fixed values, not calibration
outputs.

## Networking

Do not assume venue Ethernet or usable venue Wi-Fi.

Baseline:

```text
Pi built-in Wi-Fi: private recs-control access point
Phone/tablet: joins recs-control
Recording: works offline
```

Mixer control network:

```text
Phone/tablet
  -> Pi Wi-Fi hotspot
  -> Pi routes or bridges to Ethernet
  -> X18 Ethernet port
```

This avoids the X18 built-in Wi-Fi access point, which is known to be unreliable.
No USB Wi-Fi dongle is needed for this local control setup.

Optional internet for Twitch can come later through:

- USB Wi-Fi dongle;
- phone USB tethering;
- venue Wi-Fi if it proves reliable.

Internet must remain optional. Local recording and local control should work
without it.

## Test plan

Use weaker or already-owned hardware to learn early, but interpret failures by
failure mode.

Useful test cases:

1. Pi 3 B or other weak Pi with Raspberry Pi OS Lite.
2. X18 connected as USB audio.
3. Empty consumer 64 GB USB drive as output.
4. `recs` recording all 18 channels with `--record-everything`.
5. 2 to 3 hour first run.
6. 5 to 6 hour full burn-in run if the first run passes.
7. Repeat with the drive partly filled and erased.
8. Repeat with the actual final case/enclosure and cooling.
9. Run the Twitch streamer at the same time once the recording-only test passes.

Check after each test:

- no buffer overflow warnings;
- no dropped frames;
- expected file sizes;
- readable WAV/RF64 files;
- valid manifest;
- no kernel USB/storage errors;
- no swap pressure;
- acceptable drive and case temperature.

If a weak Pi passes, that is strong evidence that a Pi 5 will work. If it fails,
the failure mode matters:

- CPU overload may be fixed by the Pi 5.
- USB flash write stalls point to storage choice.
- Power or thermal instability points to enclosure and power design.

## Open questions

- Whether the X18 and Linux audio stack allow `recs` and the Twitch streamer to
  open the USB audio device at the same time.
- Whether a nano USB flash drive sustains the write pattern without long stalls.
- Whether the X AIR app can discover the mixer across the Pi Wi-Fi/Ethernet
  boundary, or whether manual IP entry is required.
- Whether 2 GB has enough margin once the real streamer and stage-control are
  running together.

## Additional work beyond the prompt

None.
