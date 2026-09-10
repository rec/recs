# Sample instrument scores

The canonical format, models, examples and schema now live in Ufor:

- [Instrument format](../../ufor/doc/instrument-format.md)
- [Envelope and LFO semantics](../../ufor/doc/modulation-format.md)
- [Native conversion fixture](../../ufor/conformance/instrument.json)
- [Score schema](../../ufor/schema/scores.json)

`ufor.samples.instrument.InstrumentScore` is the common root. It owns sealed
audio assets, native timebases, output layout and a typed sample-instrument body.
Slots reference named slices and explicit channel maps. `ufor.samples` owns the
musical declarations; `ufor.envelope`, `ufor.lfo` and `ufor.modulation` provide
their shared control definitions. The old Recsam classes and `format_version`
root are removed, with no forwarding modules or compatibility reader.

## Recs' application boundary

`recs/recsam/assets.py` reads audio metadata, embedded WAV loops, file size and
SHA-256. `recs/recsam/sfz.py` resolves safe local paths and supplies that metadata
to Ufor. No portable model remains defined in Recsam.

```python
from pathlib import Path

from recs.recsam.sfz import read
from ufor.codec import score_toml
from ufor.sfz import write

result = read(Path("Glass.sfz"))
if result.complete and result.instrument is not None:
    Path("instrument.toml").write_text(score_toml(result.instrument))
    exported = write(result.instrument)
```

Check `complete` and inspect `unimplemented` before accepting either conversion.
SFZ import uses Recs' explicit 48 kHz stereo output default; `output_rate` and
`output_channels` may select another supported rate/layout. Imported assets keep
their measured native rate, frames and channels. Import does not rewrite audio.
Export is pure text conversion in `ufor.sfz`; it reports nonrepresentable
envelopes, routes, channel maps, controls and other features.

For another application, use `ufor.sfz.parse`, `sample_paths`, and `compile`
with that application's asset facts and output choices. Ufor does no file I/O,
decoding, hashing, device access or waveform generation.

## Changes to authored documents

Use the [conversion instructions](../../ufor/doc/instrument-format.md#updating-old-declarations).
Move metadata to the common root, replace sample paths with sealed assets and
slice IDs, and declare output clocks/channels. Envelope overrides are complete
segment definitions. Playback overrides use explicit nullable fields so
inheritance survives serialization. Routes use structured targets and declared
source bindings. Unit strings such as `10ms` are authoring input, not native
data: normalize them before constructing Ufor models.

This changes instrument documents, not recording descriptors or production
sessions. Creating samples from edits and implementing a sampler remain deferred
in [Sample Playback](../plan/sample-playback.md).
