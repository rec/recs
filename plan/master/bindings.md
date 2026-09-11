# Implementations, endpoints, and parameter mappings

Part of the [master proposal](master.md). A binding connects a portable intent
to a concrete realization. It must make both the useful correspondence and its
limits visible.

## What a binding contains

A binding score names the logical definition or endpoint, an installed
adapter ID, implementation identity/revision, port/channel mapping, parameter
mapping, and supported capabilities. Physical bindings additionally identify
local device selectors and calibration. Credentials are resolved through local
configuration and are never included in the portable content package.

An installed adapter owns executable code, plugin discovery, library loading,
wire serialization, and calls into the implementation. A definition contains
registered operation IDs, not executable module paths. Built-in DSP, external
plugin hosts, existing application engines, and hardware endpoints can all
implement this contract without sharing a single binary ABI.

The capability declaration includes exact stream types and rates, parameter
domains and update resolution, live/offline support, latency, state restore,
determinism claim, and available failure observations. A host validates the
selected graph against it before activation. Unknown required capabilities fail
preparation; an editor can still display the unbound definition.

## Parameter mapping

Every mapped parameter names a canonical parameter ID, a stable native ID,
conversion, valid input/output ranges, and automation resolution. Native display
names are labels, not stable identifiers. A mapping can be identity, affine,
logarithmic, a monotone piecewise table, or an explicit enum table. Anything
more complex is implemented by an adapter with a named tested contract, not
embedded code in TOML.

Illustrative binding body for a hypothetical plugin with normalized logarithmic
cutoff. It makes no claim about a particular real plugin:

```toml
adapter = "example.plugin-host"
implementation = "example.filter"
implementation_revision = "1"

[[parameters]]
parameter = "cutoff_hz"
native_id = "cutoff"
conversion = "log_normalize"
input_min = 20.0
input_max = 20000.0
output_min = 0.0
output_max = 1.0
out_of_range = "reject"
```

For this mapping, `y = log(x/20) / log(20000/20)`. The endpoints map to 0 and 1;
their geometric mean maps to 0.5. Do not use a linear map because both endpoints
fit. An inverse mapping exists here, but an enum table or quantized mapping may
be many-to-one; feedback must then be reported as quantized/ambiguous rather
than falsely reconstructing the original value.

For amplitude gain, converting a positive multiplier `g` to decibels uses
`20 * log10(g)`. Zero maps to an explicit native mute or supported silence
value; it is not a finite dB value. Likewise, a fixture's unsupported gobo has
no nearest numeric meaning. Reject or require an authored substitution.

Plugin APIs expose their own parameter identities, ranges, flags, and automation
contracts. For example, CLAP's parameter interface describes parameter metadata
and parameter update behavior. Adapters must honor those contracts, rather than
assuming every knob accepts arbitrary per-sample updates.
[CLAP parameter interface](https://github.com/free-audio/clap/blob/main/include/clap/ext/params.h).

## Controls entering the graph

An input binding selects a physical control or protocol field and maps it to a
typed logical control. It declares source domain, target domain, conversion,
scope, and state reset. MIDI CC, OSC, keys, and sensor data become explicit
event/quantity streams. Routing those streams through common mappings removes
protocol interpretation from instruments and animations.

If a manual control and an automation lane both address a parameter, the work
declares priority, latch, or a mathematical combiner. A host UI must not invent
a different precedence on each machine. Record manual changes with their
resolved target and original source when reproducing the run matters.

## Portability levels

| Claim | Required evidence |
| --- | --- |
| Editable | Score schema and dependencies can be inspected without executing the implementation |
| Realizable | A selected binding satisfies the required port and parameter contracts |
| Behaviorally matched | A named operation contract has conformance examples and a declared tolerance |
| Captured result | Sealed output assets preserve the produced data irrespective of future plugin availability |

An approximate implementation is an explicit authored choice, recorded in the
run. Never substitute one silently because its name contains “compressor.”
Opaque plugin state may supplement canonical parameters for implementation-only
details. Restore opaque state first, then apply all canonical mapped parameters;
canonical values win. A binding that cannot honor this order must reject mixed
state/parameter restoration. Missing implementation means that opaque state is
inspectable as an asset but not portable behavior.

## Change from today

Replace Lyte's score-level Python `impl` resolution with adapter lookup at
preparation time. Move `DmxInstrument` patch fields, Twinkly connection fields,
and Streamo device/service selection into binding responsibilities as each
application adopts the format. Reuse actual drivers and service adapters; do
not rewrite network transports to make the score model uniform.

Showco continues owning operational setup and service actions. Recs owns the
meaning of the graph, while the selected host owns the binding's execution.
Plugin hosting is a new implementation task, with a single concrete host chosen
for the first integration. The format proposal does not require adding every
plugin SDK as a dependency.
