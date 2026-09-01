# Headless calibration trigger

## Goal

`recs` needs a field-safe way to recalibrate noise floors after setup, while it is
already running as a daemon on a headless Raspberry Pi. The machine may have no
screen, keyboard, or network connection. The operator may be on stage and have
only a few seconds to signal the action.

The target workflow is:

1. Boot the Raspberry Pi with the normal recording drive attached.
2. Set mixer and channel levels for the show.
3. Insert a dedicated command USB stick.
4. `recs` detects the command stick and requests calibration.
5. `recs` measures each selected track for 500 ms and updates its per-track
   noise-floor override in the running configuration.
6. `recs` writes a result file back to the command stick.

## Physical interface

Use a cheap USB stick as a command token.

The recording SSD or thumb drive stays mounted for audio output. A second USB
stick is used only to request operator actions. The daemon does not calibrate at
startup; it calibrates when the command stick appears while the daemon is already
running.

The command stick should contain an explicit marker file:

```text
RECS_CALIBRATE
```

The explicit marker avoids treating every inserted USB drive as a calibration
request.

## Success and failure signals

After a successful calibration, write:

```text
RECS_CALIBRATE_DONE
```

After a failed calibration, write:

```text
RECS_CALIBRATE_FAILED
```

The failed file should contain a short human-readable reason, for example:

```text
No matching input devices
```

If practical, the daemon can also flash the Raspberry Pi activity LED:

- Three fast flashes means calibration completed.
- Slow repeated flashes means calibration failed.

LED control should be best-effort only. Raspberry Pi models and OS images expose
onboard LEDs differently, so the result file on the command stick is the durable
acknowledgment.

## Daemon behavior

The daemon should watch for mounted removable drives. When a new removable mount
appears:

1. Ignore the configured recording/output drive.
2. Look for `RECS_CALIBRATE`.
3. If found, request calibration for all online tracks.
4. Measure each track for 500 ms and add `preview_headroom` to its individual
   noise-floor result.
5. Apply those values to `recording.channel_noise_floors` through the normal
   runtime configuration update path.
6. Write `RECS_CALIBRATE_DONE` or `RECS_CALIBRATE_FAILED` to the command stick.
7. Record calibration events and the resulting configuration update in the
   session record.

The operation should be one-shot per insertion. Leaving the command stick inserted
should not repeatedly recalibrate unless the marker or insertion state changes in
a defined way.

## Mounting

The main implementation risk is automounting.

On a stock Raspberry Pi OS Lite install, inserted USB drives may not be mounted
automatically. There are two reasonable approaches:

1. Configure a small udev/systemd mount rule that mounts command sticks under a
   known directory.
2. Let `recs` discover removable block devices and mount the command device
   itself.

The first option is simpler and keeps `recs` focused on recording and command
handling. The install flow can create the mount rule as part of daemon setup.

## Additional work beyond the prompt

None.
