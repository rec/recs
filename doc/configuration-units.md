# Configuration Units

Physical configuration values accept numbers in their existing units or strings
with explicit units. The same validation applies to CLI options, API `set_cfg`
values, saved settings, and per-device profiles. OSC configuration and recsam
instrument declarations use the same duration and frequency parsers.

```sh
recs --quiet-before-start 250ms --longest-file-time '2 h' \
     --ui-refresh-rate 20Hz --waveform-bucket-milliseconds 0.02s \
     --minimum-free-space 1GiB --memory-reserve-megabytes 1GB
```

## Units And Defaults

| Settings | Bare-number unit | Examples |
| --- | --- | --- |
| Recording durations, buffer duration, polling periods, device sleep | Seconds | `"10ms"`, `"2 min"`, `"1h"` |
| Waveform bucket and batch lengths | Integer milliseconds | `"20ms"`, `"0.1s"` |
| UI refresh rate | Hertz | `"20Hz"` |
| Minimum free disk space | Integer bytes | `"500MB"`, `"1GiB"` |
| Memory reserve | Integer decimal megabytes | `"500MB"`, `"1GB"` |
| OSC poll and resubscribe periods | Seconds | `"250ms"`, `"10s"` |
| Recsam envelope, smoothing, delay, and choke-fade times | Seconds | `"5ms"` |
| Recsam sample reference pitch, EQ and LFO frequencies | Hertz | `"440Hz"`, `"2.4kHz"` |

Unit strings contain a number followed by one unit name or symbol, with optional
whitespace. Scientific notation is accepted. Unit symbols are case-sensitive:
`MB` is decimal megabytes and `MiB` is binary mebibytes; `KB` is also accepted
for decimal kilobytes. Full names such as `seconds` and `kilohertz` work too.
Use `min` for minutes: Pint's ordinary `m` means metres, not minutes.
Compound expressions are not configuration syntax.

Second-valued fields also retain `MM:SS` and `HH:MM:SS` input. A bare numeric
string has the same meaning as a number. Existing zero-as-unlimited settings
remain unchanged; positive-only settings still reject zero.

Converted values must fit the field's existing type and range. Recs rejects
wrong dimensions, nonfinite values, and fractional values in integer fields.
For example, a `0.5ms` waveform bucket is invalid. A memory reserve of `1MiB`
is also invalid because it is not a whole decimal megabyte; a disk reserve of
`1MiB` is valid because it is a whole number of bytes. Conversion does not round
values silently, including when decimal input converts exactly to an integer.

## Disk Threshold Lists

Free-space alert, emergency, and pause lists accept capacities or durations:

```json
{"disk_alert_thresholds": ["1GiB", "10 min"], "disk_removable_pause": ["200MB", "30s"]}
```

Here only, the existing `10m` shorthand continues to mean ten minutes. A bare
number string means bytes. Validation normalizes capacity entries to whole-byte
strings and duration entries to second strings, for example `"1073741824"` and
`"600s"`. Duration reserves still use the measured write rate; units do not imply
a fixed relationship between time and storage.

## Storage And Runtime

Validation uses Pint and immediately extracts numeric magnitudes. Field names
and canonical units do not change: `quiet_before_start = "250ms"` becomes
`0.25`, while `waveform_bucket_milliseconds = "0.02s"` becomes `20`.
Saved settings, API replies, and configuration events use those normalized
values. Original spelling and unit choice are not preserved.

TOML and JSON unit values must be quoted:

```toml
[instrument.envelope]
attack_seconds = "10ms"
```

Pint quantities do not enter audio processing or performance-event payloads.
Frame counts, timestamps, MIDI ticks, channels, decibels, musical cents, and
normalized controls retain their existing representations. No device sample-rate
override is added by this change.
