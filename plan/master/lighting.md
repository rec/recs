# Fixture controls, DMX, and spatial light fields

Part of the [master proposal](master.md). Lighting has two principal editable
forms: semantic fixture state and spatial fields. Raw device traffic is a third
capture representation. Keep all three distinguishable.

## Fixture state

A fixture definition exposes named typed parameters: intensity, color, pan,
tilt, strobe, gobo selection, or device-specific functions. Continuous parameters
use quantities with units or a declared normalized domain. Discrete modes use
enums and hold interpolation. A fixture profile maps these to the selected
device mode's channels, packed values, and ranges.

Use degrees for a calibrated pan/tilt interface where the physical meaning is
known. Retain an explicitly named normalized-position interface when it is not;
do not label an arbitrary DMX fraction as a measured angle. A profile documents
which semantic operations a fixture cannot perform.

Two lighting sources do not automatically add like audio. A compositor declares
per-parameter rules, such as maximum intensity, ordered override, or color blend.
Discrete gobo selections never average. Competing writers to a patched address
are a validation error unless the installation declares the compositor.

## DMX and Art-Net

An authored cue targets logical fixtures and parameters. A binding supplies
fixture mode, universe, starting slot, and endpoint. This allows re-patching a
show without rewriting every cue. Keep raw DMX snapshots as ordered byte arrays
with explicit slot count and universe identity when exact capture matters.
Raw playback requires a matching patch contract and bypasses semantic remapping.

Art-Net is an output/capture transport for the selected representation, not a
new semantic quantity. Specify raw wire address and human display universe
separately. The current Lyte driver translates `universe + universe_offset` to
the wire address, normally using offset -1. Carry that choice into the binding
explicitly; do not infer it from a bare universe number.

Bindings declare multi-byte channel order, slot offsets, quantization, and
discrete value tables. For example, a profile may encode a 16-bit value into a
coarse and fine slot; this is different from driving two independent dimmers.
Keep packet sequence numbers and arrival timing in raw capture provenance.
Multi-universe output needs a declared synchronization strategy and measured
skew; saving equal timestamps does not prove simultaneous physical presentation.

## Pixel geometry

A pixel field is an array over stable element IDs, with color components and
optional alpha defined by its schema. It references a layout containing ordered
elements, coordinates, coordinate units/frame, and named regions. Lines,
matrices, rings, wearables, irregular meshes, and spatial arrangements are all
layouts of elements. Matrix row/column addressing is an authoring view of the
same stable IDs.

Illustrative small layout body:

```toml
coordinate_unit = "metre"
coordinate_frame = "installation"

[[elements]]
id = "left"
position = [0.0, 0.0, 0.0]

[[elements]]
id = "right"
position = [0.1, 0.0, 0.0]

[[regions]]
id = "pair"
elements = ["left", "right"]
```

Store pixel order explicitly. A separate physical patch maps element IDs to
device and LED indices. Rewiring a string changes that patch, not the animation.
An animation that depends on distance consumes coordinates; one that chases
along a path consumes a declared ordered region. Missing geometry is an error
for the former, not permission to assume the pixels form a line.

Use a specified linear RGB working space for the first field profile, with
explicit conversion at device output. Calibration, transfer curve, component
order, RGBW conversion, quantization, and power limiting belong to the device
profile. Do not silently call all normalized RGB arrays linear. Color fidelity
across different devices needs calibration and is not guaranteed by shared
channel names.

## Time and playback

An authored animation graph generates fields from timeline position, parameters,
and declared state. A recorded field stream keeps actual frame timestamps and
layout identity. State changes hold until the next change unless a semantic
curve specifies interpolation. A sink schedules at its supported refresh rate
and reports dropped updates; the recording retains original timing.

Stop/disconnect behavior belongs to the endpoint profile: blackout, fade, or
defined held state. Resetting all raw bytes to zero is not a universal semantic
“off” for every fixture function. Preview uses the same layout and control
resolution as physical output, with delivery replaced by visualization.

## Change from today

Lyte's `animation.Device` primarily supplies `led_count`; its frames and state
are already separate. Add layout references and explicit color interpretation
to the definition while retaining efficient runtime arrays.

`ShowFile` separates animations, mixers, devices, and run targets, but its
generic `DeviceSpec` currently supports Twinkly only. `InstallationFile` already
supports Twinkly and DMX targets and Art-Net delivery. Replace these distinct
native document roots with common graphs plus installation bindings, reusing
the existing renderers and drivers where their semantics match.

`DmxInstrument` currently combines patch address and channel categories.
Separate reusable fixture capabilities from physical patching. Preserve its
range/overlap validation. `DmxValues` already distinguishes named values from
raw integers; retain that distinction. `patches.py` region maps and MIDI
bindings become layout and control-binding definitions, respectively. Do not
assume planned generalized input controls are already implemented everywhere.
