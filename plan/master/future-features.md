# Future features worth building

Part of the [master proposal](master.md). These are suggestions, not approved
implementation work or additional fields required in every score. The first
usable milestones are in [How to implement](how-to.md). Video remains outside
the target even in this list.

Priority revision, 8 September 2026: settle the portable tuning/scale,
oscillator, envelope, and LFO model before adding audio waveform generation.
Sampler rendering is deferred; the options below are not an instruction to
resume it.

## Make the whole performance editable

| Feature | What the user gains | Prerequisite and boundary |
| --- | --- | --- |
| One multitrack editor | Audio waveforms, notes, controls, keys, fixture cues, and LED regions on a common timeline | Shared time and stream types; each lane still uses its own editing tools |
| Performance history | Select a moment and inspect what was heard, played, requested, and sent to lights | Capture journals and clock uncertainty; do not imply perfect synchronization |
| Semantic diff and merge | Review “cutoff changed from 800 to 1200 Hz” or “live segment moved 30 seconds” | Stable IDs and schemas; conflicting editorial choices remain visible |
| Named reusable scenes | Trigger a coordinated instrument, synth patch, and lighting arrangement | Explicit interfaces, instance state, and bounded transport behavior |
| Capture and replace | Freeze a processor or live performance into assets, then reopen its editable source | Provenance, state/tail rules, and dependency identity |

## Make performance instruments richer

Add linked microphone takes, named slices, reusable slot groups, and precisely
defined voice retirement after their interactions are specified. A sample
browser could create an instrument directly from selected Recs recording ranges,
retaining the original take and edit provenance.

Reproducible humanization could vary timing, pitch, dynamics, and take choice
from a documented seed and algorithm. Keep authored randomness separate from
the result of one performance, so “try another take” and “repeat this take” are
different operations.

The first [modulation profile](modulation.md) now defines envelope/LFO state and
curve semantics. Looped envelopes, random/sample-and-hold sources, and continuous
rate ramps remain later extensions requiring their own conformance cases.
Granular synthesis, convolution,
time stretching, and
physical modeling are useful later processor capabilities. Prefer binding an
existing implementation when it meets the contract. Add a new universal
parameter only when its meaning across implementations can actually be stated.

## A Small Portable Sampler Later

After the model settles, evaluate a compiled sampler core and a possible VST
instrument wrapper. An optional Python reference followed by a port is another
route, not a requirement. Keep one small specification and language-neutral
conformance cases for tuning, oscillators, envelope/LFO state, event ordering,
and voice lifecycle. Add shared audio fixtures only when waveform generation
resumes. Portability requires explicit tolerances and shared tests, not just
equivalent field names in two languages.

## Connect sound, gesture, and space

Offer reusable mappings such as breath to brightness, drum onset to a spatial
pulse, pitch to a palette position, or a keyboard gesture to a synth envelope.
Each mapping should expose its input domain, output domain, smoothing, and
latency. An editor could preview those relationships using a recorded input
before binding any device.

Layout-aware authoring could support paths, surfaces, nearest-element queries,
and transformations between installations. Explicit retargeting would let one
animation move from a ring to a wearable without pretending that their geometry
is identical. Calibration captures could describe actual brightness/color and
CV response rather than relying on factory labels.

Higher-dimensional quantities could cover position, motion, sensor telemetry,
or haptic controls. Add a typed schema and combination rule for each concrete
use, rather than making arbitrary arrays automatically routable to all devices.

## Better radio and live production

Add a rolling capture buffer for instant replay and delayed live relay, with
explicit retention limits and a clear boundary between retained and expired
material. A producer could turn the previous five minutes into a replay section
without interrupting ongoing capture.

A programme rehearsal view could substitute recorded stand-ins for future live
sources, display unresolved intervals, and estimate overrun against hard starts.
Loudness preparation could process known sections in advance while a separate
live chain manages unknown material; whole-program normalization remains an
offline operation.

An as-aired editor could compare intended and actual playout, replace a failed
remote interview with a later recording, and generate a clearly identified
edited rebroadcast. Preserve the original as-aired capture as its own work.

## Reproducibility and scale

Build render caching from sealed dependency identities, parameter values,
bindings, and state. Extend it to reusable stem/field renders only after correct
single-machine execution exists. A cache must include the selected realization,
not merely an abstract operation name.

State checkpoints could accelerate seeking and long offline jobs. Checkpoints
need implementation identity and precise event/clock position; restoring an
incompatible plugin state must fail visibly. Exposed causal feedback graphs can
follow once the scheduler honors sample-level delay independently of block size.

Distributed execution could place capture and outputs near their devices.
It requires measured clocks, bounded transport, ownership, and failure behavior;
it is a separate runtime project, not something achieved by putting hostnames
on graph nodes. Start with one transport authority and recorded observations.

## Interchange and accessibility

Provide an implementation coverage report before exchange: which parameters
are exact, which are approximate, what is unavailable, and which outputs have
been captured. Add plugin/device adapters one at a time with reusable mapping
fixtures and clear unsupported-feature reporting.

Schema-driven editors could supply appropriate controls for Hz, ratios, enum
choices, time, geometry, and tuning degrees. Accessible text authoring and
keyboard navigation should remain first-class alongside graphical timelines.
Human-friendly recipes can compile into the same canonical scores so an
operation authored in the CLI and one authored in an editor stay interchangeable.

## Suggested priority

Stages 1 and 2 have established common arrangements and native capture. Ufor
now owns the initial musical definitions and first envelope/LFO control profile.
Shared performance events and typed routes now accompany the instrument contract.
Next implement its native score, preparation, and SFZ cutover. Defer
new sampler, oscillator, and other audio generation until that design is ready
and execution work is explicitly resumed. Cross-domain and programme work can
reuse existing recordings and engines. Improve authoring and interchange around
those cases.
Defer distributed scheduling, a large plugin catalogue, and general algorithm
languages until the smaller system demonstrates a concrete need for them.

## Additional work beyond the prompt

None. The suggestions above are the requested future-feature proposals.
