# Handover

recs is pinned to the uFor revision that provides inline-score automation. The
edit package has been migrated from uFor's retired arrangement-local automation
API, and generated crossfades are persisted as inline automation scores.

Inline automation already requires the arrangement's exact audio rate; mismatched
rates are rejected by `Renderer._automation`. General control-rate conversion
remains a separate design decision, not an unfinished same-rate migration.

Sources and intermediate edit outputs use temporary float32 storage, with
bounded rendering, automation, normalization, and encoding buffers. See the
[runtime package map](runtime-architecture.md) and [arrangement format](arrangement-format.md).

uFor owns portable instrument semantics; enge owns both synth and sampler engine
implementation. recs owns capture, editing, encoding, and future host integration.
The [enge handover](../plan/enge.md) and [instrument playback boundary](../plan/sample-playback.md)
supersede the earlier model-first waveform-generation pause.
