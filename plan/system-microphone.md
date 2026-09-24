# System microphone privacy policy

## Goal

Do not expose or record the operating system's current default input device
unless the user explicitly opts in. Add the top-level configuration field:

```python
record_system_mic: bool = False
```

When it is false, recs must remove that device before it becomes an input device
or a live-device snapshot. It must consequently be absent from normal listings,
aliases, selection, readiness, control status, source lifecycle events, and
capture.

## Definition

The system microphone is an input endpoint which the operating system's native
audio-device API positively identifies as an integrated microphone. It is not
the current default input. A default input can be an external interface,
headset, virtual device, aggregate, or no device at all.

The probe must establish an authoritative bridge from the native endpoint to a
specific PortAudio input-device index. It must not correlate devices by display
name, channel count, sample rate, enumeration order, or any other heuristic.
If either the native classification or that identity bridge is unavailable,
the probe returns no system microphone. An unclassified input remains an
ordinary input device.

## Platform rules

### macOS

Use CoreAudio, not the default-input property. A candidate must be an input-capable
`AudioDeviceID` whose `kAudioDevicePropertyTransportType` is
`kAudioDeviceTransportTypeBuiltIn`. The platform adapter must prove its CoreAudio
device UID maps to the PortAudio device index before returning that index. USB,
Thunderbolt, Bluetooth, aggregate, virtual, HDMI, and unknown transports are
not system microphones.

### Windows

Use the MMDevice and DeviceTopology APIs for capture endpoints. A candidate
must have microphone form factor, an internal general location, and a capture
pin category of microphone or microphone array. Its endpoint ID must be proven
to map to the PortAudio/WASAPI device index. An endpoint missing any of those
properties, an endpoint on USB/Bluetooth/network/display transport, a headset,
a line input, or a device without an authoritative mapping is not classified.

### Linux

There is no Linux-wide native contract that identifies a physical built-in
microphone and maps it to a PortAudio input. The initial Linux adapter always
returns no system microphone. It must not infer one from ALSA card numbers,
`/sys` topology, udev names, PipeWire descriptions, PulseAudio defaults, or
device-name strings. A later backend-specific implementation is valid only if
it has a documented, stable endpoint-to-PortAudio identity bridge and a native
integrated-microphone classification with the same level of proof as the macOS
and Windows rules.

## Design

The internal `query-devices` and `query-devices-stream` helper protocol should
return a device-inventory envelope, not only a bare device list. The envelope
contains raw PortAudio records plus an optional set of PortAudio input-device
keys classified by the platform adapter. It is local, short-lived discovery
metadata. It is never written into settings, a session record, or status.

Centralise policy filtering in `recs.cfg.device`, before construction of
`InputDevice` objects. The filter accepts the inventory and
`record_system_mic`; it removes only positively classified system microphones
when the setting is false. All consumers must use this one filtered path. No
default-device, device-name, or post-capture suppression is permitted.

`record_system_mic` belongs to the top-level `General` configuration surface,
so ordinary CLI spelling is `--record-system-mic` and the flattened `Cfg`
field is `record_system_mic`. It is a startup discovery policy, not a mutable
live control: changing it requires the next recs start. It is not saved in the
mutable settings overlay. A named project may still explicitly contain the
startup setting like other non-mutable configuration.

The default must be applied to all host-discovered inputs, including the
initial `Cfg.input_devices` inventory, the background `DevicePoller`,
`recs --info`, readiness, and every downstream device/status listing. A
user-supplied `--devices` file is also filtered only when its source key matches
a positively classified system-microphone key; an explicit file does not
silently bypass the privacy policy. File sources and MIDI/OSC discovery are
unaffected.

## Implementation steps

1. Define a small platform-probe interface that returns only proven PortAudio
   input indices. Implement it in the minimal query helper, preserving its
   no-capture and PortAudio-error behavior. Keep the helper free of recorder
   configuration and lifecycle imports.
2. Implement the macOS CoreAudio adapter and its identity bridge first. Add the
   Windows adapter only with the complete MMDevice, DeviceTopology, and WASAPI
   identity evidence above. The Linux adapter returns an empty result. Each
   adapter fails closed: an unavailable framework, denied query, malformed
   property, unsupported host API, or incomplete mapping returns no candidate.
3. Add a typed inventory envelope in the device-configuration layer, containing
   raw device records and the positively classified source keys. Do not add a
   default-device field.
4. Add `General.record_system_mic`, defaulting to `False`, with concise CLI
   help describing the opt-in. Thread the value through initial inventory
   lookup, `--info`, readiness, and `DevicePoller`. Make the polling stream
   filter each fresh inventory before queuing a snapshot, so a newly selected
   positively classified microphone never briefly appears as a source.
5. Make `get_input_devices` the single policy boundary for both live inventory
   and `--devices` JSON. Supply the live system-microphone identity when
   interpreting static definitions, and filter before aliases, include/exclude
   resolution, saved tracks, or `DeviceLifecycle` can see the source.
6. Audit all device-list responses and documentation. `recs --info`, readiness
   reports, control `devices`/status output, and user-facing error text must
   operate on the filtered inventory. The internal helper remains an
   implementation detail and must not be advertised as a way around the
   privacy default.
7. Document the default, the explicit opt-in, and the platform-specific
   classification rules. State clearly that unclassified devices are retained,
   especially on Linux, and that changing native device identity affects later
   discovery snapshots, not an already-running source.

## Tests and acceptance

- macOS fixtures with a proven built-in CoreAudio input and an external
  interface yield only the interface from `Cfg.input_devices`, `recs --info`,
  readiness, and `DevicePoller` when `record_system_mic` is false.
- With `record_system_mic=True`, the same inventory exposes both devices and
  the microphone can be selected and captured normally.
- Windows fixtures require all native microphone, internal-location, topology,
  and WASAPI-mapping evidence. Missing any one of them retains the device.
- Linux fixtures always retain inputs regardless of names, ALSA card numbers,
  PipeWire/PulseAudio defaults, or udev/sysfs topology.
- A `--devices` JSON definition that matches a positively classified
  system-microphone key is filtered under the default policy and retained only
  by explicit opt-in.
- Missing, stale, malformed, output-only, unsupported-host-API, or
  unbridgeable native metadata does not hide an unrelated input or prevent
  external device discovery.
- A polling sequence where native classification changes never introduces a
  newly classified microphone while the policy is false. It may introduce a
  previously suppressed device after it is no longer classified.
- Aliases, include/exclude selectors, saved track layouts, and control requests
  cannot resurrect a filtered microphone. They fail or report absence in the
  same way as any unavailable input.
- Existing device, poller, readiness, CLI-help, and recorder lifecycle tests
  continue to pass. Add focused fixtures for default-device metadata rather
  than consulting the host microphone during tests.

## Additional work beyond the prompt

None.
