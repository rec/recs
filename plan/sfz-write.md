# SFZ Export

## Goal

Add deterministic, best-effort SFZ serialization for a validated recsam
`SampleInstrument`. The exporter returns the SFZ text and a complete ordered
collection of recsam fields or features that it could not represent. It does
not write a file or modify sample assets.

The primary goal is behavioral round-trip compatibility for completely
converted SFZ files:

```python
first = sfz.read(source_path)
assert first.complete
assert first.instrument is not None

exported = sfz.write(first.instrument)
assert exported.complete

output_path.write_text(exported.contents)
second = sfz.read(output_path)
assert second.complete
```

`source_path` and `output_path` are in directories containing equivalent sample
assets. The two SFZ texts need not be lexically identical and the second recsam
object may express documented SFZ defaults differently. Recs metadata comments
must preserve names, IDs, descriptions, and tags; playable behavior must be
equivalent for every trigger, release, and supported control input.

The first implementation must therefore cover every construct that the current
importer can convert completely, including compatibility opcodes such as
[`region_label`](https://sfzformat.com/opcodes/region_label/) which the importer
already accepts even though the [SFZ opcode catalogue](https://sfzformat.com/opcodes/)
classifies it as an ARIA extension. It must not silently approximate values,
discard behavior, or claim that an incomplete export is lossless.

## Public API

Add this entry point to `recs.recsam.sfz`:

```python
def write(instrument: SampleInstrument) -> SfzWriteResult:
```

`SfzWriteResult` is a frozen Pydantic data class:

```python
class SfzWriteResult(base.Model):
    contents: str
    unimplemented: list[UnimplementedFeature] = Field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.unimplemented
```

`contents` always ends with one newline. It can contain a useful partial SFZ
when `complete` is false. An export with no representable slots contains only
the generated-file comment and remains incomplete.

`complete` means that all playable behavior and metadata were represented.
Canonical structures created by `read()`, including generated region IDs, the
filename-derived instrument name, and implicit sustain declarations, must be
representable by the exporter so they do not make an otherwise complete round
trip incomplete.

Keep `write()` distinct from filesystem operations. A later convenience
function may write `contents` to a caller-selected path, but that is not part of
this work.

## Shared diagnostics

The import and export paths should share `UnimplementedFeature`, but not the
current SFZ-specific location fields. Replace those fields with a discriminated
location:

```python
class SfzLocation(base.Model):
    kind: Literal['sfz'] = 'sfz'
    header: str
    opcode: str | None
    line: int
    column: int


class RecsamLocation(base.Model):
    kind: Literal['recsam'] = 'recsam'
    path: str


class UnimplementedFeature(base.Model):
    location: Annotated[
        SfzLocation | RecsamLocation,
        Field(discriminator='kind'),
    ]
    value: str | None
    reason: str
```

This is useful reuse: callers receive one issue type and common `value` and
`reason` fields, while each direction retains an exact and valid source
location. Do not put nullable SFZ and recsam location fields together in one
flat model.

Import diagnostics retain their current information through `SfzLocation`.
Export paths use stable, zero-based Pydantic-style paths such as
`instrument.tags[1]`, `slots[0].mapping.minimum_velocity`, and
`slots[2].crossfades[0]`. Diagnostics are returned in model traversal order,
with parent-level issues before their children.

Use `value` for a concise canonical rendering of the rejected value. A complex
object should use its compact JSON representation rather than `repr()`. Reasons
must explain the missing SFZ concept or exact representability constraint, not
merely say "unsupported".

## Export policy

The generated text is best-effort, but every emitted opcode must preserve the
corresponding recsam behavior exactly within SFZ's model.

Apply these rules:

1. Inspect every instrument and slot field even if another issue already makes
   that scope incomplete. Return all independently identifiable omissions.
2. Omit an unsupported optional field and report it.
3. Omit an entire slot when its sample reference, selection bounds, velocity
   bounds, or other eligibility-defining data cannot be represented. Emitting a
   broadened or differently pitched region would be misleading.
4. Emit a slot with its representable subset when an unsupported processing or
   playback detail can be omitted without making the remaining text invalid.
   The issue collection remains the authoritative indication that playback is
   incomplete.
5. Never round, clamp, normalize, or choose a nearest supported value silently.
6. Treat an invalid `SampleInstrument` as a programming error. `write()` accepts
   the validated data class, so it does not duplicate model validation.

## SFZ structure

Emit one self-contained `<region>` block per representable slot. Do not add
`<global>`, `<master>`, or `<group>` optimization in the first implementation.
Flatten inherited instrument and slot declarations into each region. This
avoids changing meaning through SFZ inheritance and makes one bad slot
independent of the others.

Within every region, emit opcodes in one fixed order:

1. label and sample;
2. key, velocity, and pitch mapping;
3. trigger and choke behavior;
4. playback mode, direction, frame bounds, and loop;
5. volume, tuning, and spatial processing;
6. amplitude envelope;
7. supported modulation points.

Use one opcode per line and one blank line between regions. Output order follows
`instrument.slots`; it must not sort slots or rely on dictionary iteration.

Use locale-independent shortest round-trippable decimal formatting, normalize
negative zero to zero, and emit integer syntax for integral SFZ fields. Reject
non-portable sample values containing newlines, comments, headers, or text that
the SFZ tokenizer could interpret as another opcode. Spaces and portable path
separators remain valid. Do not invent an escaping syntax that SFZ players may
not understand.

## Initially representable fields

Implement the following conversions first.

### Identity and assets

- `slots[*].sample` becomes `sample`.
- `slots[*].name`, when present, becomes `region_label`, matching the importer.
- Preserve instrument name, descriptions, tags, slot IDs, and slot tags in
  deterministic `// recs:` metadata comments. Define a JSON-valued comment
  syntax rather than an informal human-only rendering, and teach `read()` to
  restore it. Generic SFZ players safely ignore these comments.
- Emit these comments consistently, including for filename-derived names and
  parser-generated IDs. The extra comments do not change generic SFZ playback,
  and a second recsam import can then preserve the exact metadata without
  requiring unavailable provenance flags.

Use exactly these two comment records:

```sfz
// recs:instrument {"version":1,"name":"Glass","description":null,"tags":[]}

// recs:slot {"id":"region-1","name":null,"description":null,"tags":[]}
<region>
sample=glass.wav
```

The instrument record occurs once before all SFZ headers. A slot record occurs
immediately before the region it describes and binds only to that region. JSON
uses compact separators, preserves Unicode, and escapes embedded newlines.
Malformed recognized records are input errors; an unknown metadata version is
an unimplemented feature. Unknown ordinary comments remain ignored. Do not use
metadata comments to hide unsupported playback, selection, processing, or
controller behavior.

### Mapping

- Inclusive key bounds become `lokey` and `hikey`. A single-key range may use
  `key` only when doing so does not alter pitch-center behavior.
- SFZ's key domain is 0 through 127. Omit a slot whose recsam bounds fall
  outside it.
- Velocity bounds become `lovel` and `hivel` only when each value is exactly an
  integer divided by 127. Omit the slot rather than quantizing another value.
- `pitch_tracking=false` becomes `pitch_keytrack=0`.
- A reference pitch attached to an untracked slot is metadata in recsam but is
  discarded by the current SFZ importer when `pitch_keytrack=0`; report it
  rather than emitting a `tune` value that would change playback.
- For tracked slots, choose the nearest in-range equal-tempered
  `pitch_keycenter` and use an exact `tune` residual so importing the result
  reconstructs the same reference pitch and static tuning. Specify and test the
  formula with `440 Hz` at key 69. If SFZ's numeric precision or range cannot
  preserve the value, omit the slot and report the reference pitch.
- `event_key` and sustain-transition mappings are unexportable until their SFZ
  controller semantics can be represented.

### Playback and triggering

- Forward and backward directions become `direction=forward` and
  `direction=reverse`. Mirror direction is reported and omitted.
- One-shot and held playback become the corresponding `loop_mode` values.
- Convert recsam's exclusive `end_frame` and loop `end_frame` to SFZ's inclusive
  `end` and `loop_end` in one shared helper. Preserve zero-based starts.
- Map `until_release` and `through_release` to `loop_sustain` and
  `loop_continuous`.
- Report loop crossfades because the importer/export subset does not yet define
  an exact SFZ conversion.
- Map start, release, and logical-release triggers to their exact SFZ trigger
  values. Report sustain-press and sustain-release triggers.

### Processing and envelopes

- Combine instrument and slot static volume and tuning according to recsam's
  composition rules, then emit `volume`, `transpose`, and `tune` without
  rounding. Ensure pitch-reference compensation and static tuning are combined
  once.
- Combine instrument and slot spatial settings according to recsam's additive
  composition rules. Emit `pan` for exactly one applicable nonzero combined
  pan or stereo-balance value. Report a conflict when both are nonzero. The
  exporter does not inspect assets, so document that the referenced sample
  layout must match the recsam field's mono or stereo meaning.
- Emit delay, attack, hold, decay, sustain, and release amplitude-envelope
  values after resolving instrument inheritance.
- Export only SFZ's representable envelope shapes. Report a field whose recsam
  shape differs from the corresponding SFZ curve.
- Report equalizer bands, named envelopes, LFOs, and generated modulation until
  exact SFZ mappings are implemented.

### Selection, choking, and modulation

- Allocate stable positive SFZ group numbers for arbitrary recsam choke-group
  IDs, ordered by first slot occurrence. Map one immediate or release choke to
  `group`, `off_by`, and `off_mode`. Report fade choking and slots with multiple
  choke targets.
- Report alternate selection sets initially. Do not guess SFZ sequence or
  random grouping semantics.
- Export key or velocity layer crossfades only when their endpoints map exactly
  to SFZ integer key or velocity points and their curve has an exact SFZ
  counterpart. Report control crossfades and unsupported curves.
- Export amplitude-by-velocity modulation as `amp_veltrack` and
  `amp_velcurve_N` only when every input point lies exactly on `N / 127` and the
  operation and interpolation match SFZ. Report all other modulation routes.
- Report named controls, sustain configuration, articulations, and controller
  modulation. They require the separate input-binding format described by the
  SFZ import plan.
- Recognize the canonical sustain control and threshold created by `read()` as
  SFZ's implicit sustain-pedal behavior and emit no diagnostic for it. Report
  absent or different recsam sustain behavior when it cannot match the target
  player's implicit behavior. Custom control identities and thresholds require
  a binding document.

## Implementation structure

Keep parsing and serialization in `recs/recsam/sfz.py` while the supported
surface is small. Introduce private conversion helpers grouped by recsam scope:

- instrument-wide preparation and choke-group allocation;
- slot eligibility and region generation;
- mapping, playback, processing, envelope, and modulation conversion;
- numeric and endpoint formatting;
- issue construction using a recsam field path.

Helpers should return opcode data, not concatenate fragments independently.
Represent a region internally as an ordered `list` of small opcode data
classes, then use one serializer for token formatting and whitespace. This
keeps ordering, numeric formatting, and unsafe-value checks centralized.

Do not introduce an intermediate generic sampler format, a plugin system, or a
second SFZ parser.

## Tests

Add focused tests alongside the SFZ importer tests:

- every existing importer fixture whose read result is complete exports with no
  issues, and reading the generated SFZ reconstructs equivalent playable
  behavior;
- a minimally configured recsam instrument produces stable regression text and
  an empty issue list when all of its behavior is in the supported subset;
- Recs metadata comments preserve instrument and slot names, IDs, descriptions,
  tags, Unicode, and embedded newlines through recsam-to-SFZ-to-recsam tests;
- every supported mapping, playback, trigger, processing, envelope, choke, and
  velocity-modulation conversion;
- half-open recsam endpoints become inclusive SFZ endpoints;
- exact and inexact `N / 127` velocity bounds;
- arbitrary reference pitches and static tuning compose correctly;
- unsafe sample strings omit their slot;
- unsupported instrument fields, slot fields, and nested collection items
  produce complete ordered recsam paths;
- one bad slot does not suppress valid regions;
- an entirely unexportable instrument still returns valid text and all issues;
- deterministic output across repeated calls;
- export followed by import preserves the supported playable behavior.

Round-trip tests must create one-second, 48 kHz WAV assets because the importer
reads sample metadata. Compare a canonical supported-behavior projection rather
than source SFZ text. For complete recsam exports, compare the full reconstructed
model after accounting only for documented canonical SFZ defaults; the Recs
metadata comments preserve IDs and metadata.

Keep malformed-SFZ import tests separate from export diagnostics. Exporting a
valid but unrepresentable recsam value is not a parser error.

## Documentation

Update `doc/sample-format.md` to describe `SfzReadResult`, the shared diagnostic
location model, `sfz.write()`, partial-output behavior, and the exact supported
export subset. Correct its current statement that `sfz.read()` directly returns
`SampleInstrument`.

## Commit sequence

Each step should be independently tested and committed.

1. Generalize `UnimplementedFeature` locations and migrate importer tests.
2. Add the round-trip test harness and versioned Recs metadata comments.
3. Add `SfzWriteResult`, deterministic region serialization, and core sample and
   mapping export.
4. Add playback, trigger, processing, and envelope export.
5. Add choking, crossfade, and supported velocity-modulation export.
6. Add exhaustive omission diagnostics, complete-fixture round trips, and
   documentation.

## Completion criteria

- `write()` performs no filesystem I/O and always returns deterministic SFZ
  text.
- `complete` is true exactly when every recsam declaration was represented; do
  not redefine it to ignore metadata or identifiers.
- Every SFZ fixture accepted completely by `read()` can be written completely,
  and the generated SFZ reads back to equivalent playable behavior.
- Every omitted field or feature has one precise recsam location, value, and
  reason.
- No invalid or silently approximated region is emitted.
- The importer retains equally precise SFZ token diagnostics through the shared
  issue model.
- Supported exported behavior survives an export/import round trip.
- The full test and static-check suite passes without accessing MIDI hardware.

## Additional work beyond the prompt

None.
