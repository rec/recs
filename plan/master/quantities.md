# Sampled quantities, curves, and physical controls

Part of the [master proposal](master.md).

## Quantity types

A numeric stream declares both what a value means and how it is represented.
The semantic quantity, unit, scalar type, shape, and timebase are required.
The range is a domain constraint, not a substitute for a unit.

| Quantity | Canonical meaning | Typical representation |
| --- | --- | --- |
| Audio amplitude | Linear amplitude relative to declared full scale | Float samples, time by named channels |
| Gain | Linear multiplier; zero is mute and one is unity | Scalar or curve |
| Level | Decibels with reference named, such as dBFS | Analysis stream or processor parameter |
| Frequency | Hertz, with positive values where pitch is defined | Scalar, curve, or sampled control |
| Expression | Named dimensionless unipolar or bipolar control | Curve or control-change event |
| Position/orientation | Named coordinate frame, metres or degrees | Vector quantity |
| Voltage | Volts relative to the endpoint's electrical reference | Sampled array or curve |
| Gate | Logical inactive/active state | State-change events, rendered to voltage by a binding |
| Light | Linear color components and intensity in a declared color space | Spatial field described in [Lighting](lighting.md) |

Do not treat a number in `[0, 1]` as interchangeable across these types. A gain
of 0.5, a MIDI expression of 0.5, and a 0.5 V signal have different meanings.
Use explicit conversion nodes. A parameter schema fixes its canonical unit,
so every value need not repeat that unit. Editors may display convenient units
and convert before saving. Schema units can map to existing vocabularies;
LV2 already describes units on ports and some conversions.
[LV2 Units](https://lv2plug.in/ns/extensions/units).

## Sampled arrays

A sampled stream specifies rate, ordered named axes, scalar encoding, and
quantity. Audio names its channel layout explicitly. A channel index is
zero-based in this proposed model; device channel numbering belongs in the
binding. Reshaping, selecting channels, downmixing, and rate conversion are
declared operations. DSP may exceed audio full scale internally; clipping or
limiting belongs to the output contract, not every intermediate array.

A fragment connects asset frame zero or another asset offset to a native
timeline position and frame count. The recording manifest describes missing
intervals. Filling an audio gap with zero for listening does not turn lost
samples into measured silence.

## Curves and parameter automation

A curve contains ordered `{tick, value}` knots and interpolation `hold` or
`linear`, plus a timebase and target quantity. Knots are strictly increasing.
Before the first knot use the instance's base parameter value; after the last
knot hold its value. A clip limits the interval over which its curve is active.

`hold` is mandatory for enums, gates, and booleans. Linear interpolation operates
in the declared canonical unit. A logarithmic frequency sweep must use an
explicit log-domain mapping; it is not a host preference. Equal-power audio
crossfades are a paired mix operation, not a generic interpolation for arbitrary
quantities. Preserve an existing standalone equal-power gain lane by storing
linear knots in squared gain and applying an explicit nonnegative square-root
mapping. This reproduces `sqrt((1-t)*a*a + t*b*b)` without treating that rule
as interpolation for voltage, pitch, or an enum. With no instance override,
the base parameter value is its declared default.

At a parameter, a direct automation lane replaces the base value. Additional
modulation is allowed only through a declared combiner such as additive volts
or multiplicative gain. Reject competing writers without one. Scope can be
global, part, or voice; its lifetime must match the owning object.

## CV and gates

Keep pitch in Hz, expression dimensionless, and actual measured/output voltage
in volts. A pitch-to-voltage mapping names reference frequency `f0`, reference
voltage `v0`, and volts per octave `s`: `v = v0 + s * log2(f / f0)`.
For a chosen profile with `f0 = 440 Hz`, `v0 = 0 V`, and `s = 1 V/octave`,
880 Hz requests 1 V. This is an example calibration, not a universal device
standard. Linear Hz/V and other devices need their own mappings.

An endpoint profile must specify supported electrical range, calibration,
output rate, gate levels, and stop/disconnect state. “5V control” alone does
not specify polarity, pitch law, or permissible input voltage. The plan must
not assume that an arbitrary audio output can produce calibrated DC.

Declare out-of-range behavior as reject or clamp, with any clamping reported.
Separate a logical gate from its physical active voltage. A short trigger pulse
has an explicit duration and minimum supported sink resolution. On transport
stop, apply the profile's idle values; zero volts is not universally silence.

## Analysis results

An audio-to-pitch processor emits frequency plus a separate validity/confidence
signal. Zero Hz is not a substitute for “unvoiced.” A feature record identifies
the input observation interval, effective timestamp, and the later time at
which the result became available. Offline alignment can place the result at
the analyzed moment; live routing respects the analysis delay.

Keep loudness, envelope, onset events, and spectral arrays as distinct types.
Derived streams reference the source and processor run so a user can regenerate
them without confusing them with the original measurement.

## Change from today

Recs audio blocks remain efficient NumPy arrays at runtime. Add descriptors
around stored and routed streams, not one Python object per sample. Recsam's
`Control` polarity/default becomes a dimensionless specialization of the common
parameter contract. Preserve the existing distinction between linear edit gains
and recsam decibel parameters during conversion. Voltage and feature validity
are new contracts; neither can safely inherit audio defaults.
