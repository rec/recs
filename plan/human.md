# Human And Experimental Verification

## Purpose

This is the single checklist for Recs behavior that requires real recordings,
physical devices, deployed hardware, third-party applications, or performance
measurement. Automated checks remain in the feature plans and test suite.

Use expendable media for failure tests and back up source recordings. For every
run, record the Recs revision, date, host, operating system, configuration,
connected devices, and resulting session-record path in a test note.

## Autocalibration On A Noisy Session

1. Back up the uncalibrated session that motivated autocalibration.
2. Listen to every affected track. Note source-frame or wall-clock ranges for
   noisy silence, quiet program material, attacks, and releases.
3. Inspect the proposed thresholds without writing output:

   ```console
   recs edit autocalibrate /path/to/session-record.jsonl --dry-run
   ```

4. Check that every track has a plausible first-silence range and that noisier
   tracks receive a higher threshold than quieter tracks.
5. Render to a new directory and validate its record:

   ```console
   recs edit autocalibrate /path/to/session-record.jsonl \
     --destination /path/to/autocalibrated-session
   recs record check /path/to/autocalibrated-session/session-record.jsonl
   ```

6. Compare source and result track by track. Count false retained regions,
   missed quiet material, and boundaries that cut audible attacks or releases.
7. Run the generated `edit.toml` into another destination. Confirm it uses the
   stored thresholds and produces the same files and frame ranges.

Pass when record checking reports no errors, expected material is retained,
known noise-only regions are omitted, and the resolved edit is repeatable.

## MIDI Recording And Rediscovery

1. Connect a MIDI controller and identify its exact input name. Start Recs with
   MIDI enabled and, if needed, select it with `--midi-include NAME`.
2. Record for at least two minutes while playing isolated notes, chords,
   controls, and closely spaced events. Independently note the times of several
   events.
3. Stop cleanly. Open the file under `midi/` in another MIDI application and
   check event order, channel, values, note durations, and approximate timing.
   Run `recs record check` on the session record.
4. Start Recs with the selected controller disconnected. Confirm status says
   `waiting`, audio continues, and no MIDI file is created yet.
5. Attach the controller, play events, disconnect it, reconnect it, and play
   more events without restarting Recs.
6. Confirm status follows the connection state, separate files cover each
   connected period, and the session record contains matching lifecycle entries
   without repeated warning floods.
7. Repeat the complete procedure on macOS and Raspberry Pi.

Pass when both hosts produce readable, correctly timed MIDI files and hot-plug
cycles do not interrupt audio recording.

## OSC With A Real X18

1. Put Recs and the X18 on an isolated local network. Create an OSC node file
   with the documented `/xremote` subscription and a 10-second resubscription
   period.
2. Start Recs with `--osc-nodes /path/to/nodes.toml` and record for at least one
   minute.
3. Change several mixer controls at noted times while watching the OSC JSONL
   file size.
4. Capture UDP traffic with `tcpdump` or Wireshark. Confirm `/xremote` is sent at
   startup and approximately every 10 seconds, without a rapid retry loop.
5. Stop Recs, decompress the JSONL if configured, and match incoming records to
   the mixer changes. Run `recs record check` and
   `recs explain /path/to/session-record.jsonl`.
6. Temporarily disconnect the mixer network while audio continues, then restore
   it. Confirm the OSC failure is visible and isolated from other recording.

Pass when subscription cadence, recorded mixer data, session entries, and
failure isolation match the configuration.

## Live Waveforms

1. Start an 18-channel, 48 kHz recording on the Raspberry Pi with normal target
   storage and no waveform subscriber. For five minutes, record CPU, resident
   memory, dropped frames, and callback queue high-water marks.
2. Connect a public-protocol client, call `subscribe_waveforms`, and display a
   continuously scrolling 20-second window for at least ten minutes.
3. Exercise mono tracks, a stereo track on hardware channels 2-3, digital
   silence, clipping, track reconfiguration, and a source restart.
4. Pause client consumption long enough to drop waveform batches, then resume.
   Confirm the display advances to current data and represents the sequence gap
   instead of accumulating latency.
5. Call `unsubscribe_waveforms`. Confirm waveform CPU activity and queued data
   return to the unsubscribed baseline.
6. Compare subscribed and unsubscribed resource use and recording drops. Record
   screen video so scrolling smoothness can be reviewed.

Pass when scrolling is smooth at ten batches per second, layout changes remain
coherent, client stalls stay bounded, and waveforms cause no recording drops or
unacceptable sustained resource increase.

## Editing And DAW Interoperability

1. Select a real Recs session containing stereo tracks and silence-induced
   gaps. Include an 18-channel session when available.
2. Use `recs edit clip`, `split`, `stitch`, and `mix` to make separate test
   sessions. Include overlapping clips, aligned stems, and an equal-power
   crossfade. Retain each generated `edit.toml` and session record.
3. Run `recs record check` on every result. Note each output's declared start
   frame, channel count, and sample rate.
4. Import the files into the target DAW without normalization, stretching,
   channel conversion, or sample-rate conversion. Position them from their
   declared source frames.
5. Compare transients across stems, audition every channel, inspect silent gaps,
   and listen across clip and crossfade boundaries.
6. Re-render one canonical `edit.toml` and confirm the second import aligns in
   exactly the same way.

Pass when channel order and frame alignment are exact, gaps remain correctly
positioned, transitions have no unexpected discontinuities, and reruns agree.

Before retiring `~/code/fmix`, use Recs for at least three representative real
editing jobs, including one multitrack mix and one edit with gaps. Record every
workflow or output that still requires fmix. Retire it only when that list is
empty or explicitly accepted.

## Materialized Composition Resources

1. Choose short, medium, and large lossless sessions, including the normal
   maximum channel count. Preserve enough free RAM to avoid endangering other
   work during the initial runs.
2. Create a composition containing clips, routing, automation, normalization,
   and autocalibration. Run its dry run and record the estimated peak bytes.
3. Execute it with `/usr/bin/time -l` on macOS or `/usr/bin/time -v` on Linux.
   Record peak resident memory, elapsed time, CPU time, and swap activity.
4. Produce the equivalent chain as standalone lossless edits. Compare final
   samples and session-record frame ranges with the composed result.
5. On a disposable test host, repeat with an estimate close to available RAM.
   Confirm allocation failure is clear and creates no intermediate sessions or
   disk-backed fallback.

Pass when peak memory is consistent with the conservative estimate, supported
runs do not unexpectedly swap, outputs match the standalone chain, and failure
leaves truthful final-output state.

## Removable Media And Source Faults

These checks cover the remaining hardware validation in `possible-issues.md`.
Use only expendable USB media.

1. Start a multichannel X18 recording and confirm files and the session record
   are advancing.
2. Separately test a full disk, unplugged disk, read-only mount, deliberately
   slow disk, and removal followed by remounting. Note the last frame, status,
   `awaiting card`, logs, and audio, MIDI, and OSC backlog behavior.
3. Insert another suitable disk. Confirm Recs switches automatically, creates a
   new session directory, flushes backlog in order, and resumes current data.
4. Accidentally unmount and then remount the original disk. Confirm Recs uses it
   immediately.
5. Exercise the replacement timeout while the original disk remains mounted.
   Confirm Recs returns to it after the configured interval and flushes backlog.
6. During another recording, disconnect and reconnect X18 USB audio. Confirm the
   real child process stops cleanly, final record entries stay ordered, late
   updates do not corrupt status, and capture resumes when the device returns.

Pass when completed media survives, every discontinuity appears in the session
record, status identifies the active disk and source state, and no stale child
writes to an unavailable volume.

## Network Isolation

This check validates that the OSC network isolation is effective in production.

1. During a long recording, disable Wi-Fi and Ethernet, break DNS, and stop any
   remote streaming or update service. Confirm local audio, MIDI, OSC, status,
   and session records continue without growing latency or dropped frames.

Pass when network failures cannot block local recording or make local status
stale.

## Raspberry Pi Capacity

1. Record all 18 X18 channels using production sample rate, subtype, format,
   daemon GUI, MIDI, OSC, live status, and disk-switch monitoring.
2. Run for at least one hour on the target Raspberry Pi and production-class
   removable media. Include ordinary control traffic and a waveform subscriber.
3. At least once per minute, sample CPU by process, resident memory,
   temperature, write latency, callback queue high-water marks, dropped frames,
   and free disk space.
4. Perform one card replacement and one source disconnect/reconnect. Validate
   the resulting session record and every finished media file.

Pass when there are no unexplained dropped frames, memory remains bounded, the
CPU does not thermally throttle, queues recover, and write latency retains a
documented safety margin.

## Sampler Backend And Live Playback

1. Build a conformance instrument covering forward, backward, and mirror
   direction; loops; envelopes; modulation; alternate selection; choking;
   stereo layout; and deterministic selection.
2. Render one fixed event stream with each candidate backend and a simple
   reference implementation. Compare timing, duration, pitch, channel layout,
   selection order, and samples where exact agreement is expected.
3. Repeat at block sizes 64, 128, 256, and 1024 frames. Confirm timing and
   deterministic selection do not depend on block size.
4. Test realistic instruments at increasing polyphony. Measure CPU, resident
   memory, cache size, render time, and underruns with shared and multichannel
   sample assets.
5. On target hardware, measure input-to-audio latency with a loopback recording,
   including expected peak CPU and storage load.
6. Document every recsam behavior that cannot be represented exactly. Reject a
   backend that silently changes required semantics.

Pass when the selected backend has an explicit compatibility boundary, stable
block-independent behavior, bounded sample memory, and acceptable measured
latency and underrun rates.

## Additional work beyond the prompt

None.
