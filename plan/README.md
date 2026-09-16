# Plans and ownership

## Where to start

Checked 16 September 2026. Use implemented format documentation for supported
behavior, project handovers for ownership, and the owning project's plan for
remaining work. A historical milestone or test count is not current status.
Proposals do not authorize implementation by themselves.

| Question | Current source | Status |
| --- | --- | --- |
| recs behavior and structure | [Runtime architecture](../doc/runtime-architecture.md), [handover](../doc/handover.md), [README](../README.md) | Implemented recs behavior |
| Recording and editing formats | [Recording format](../doc/recording-format.md), [arrangement format](../doc/arrangement-format.md) | Implemented contracts |
| Portable instrument semantics | [uFor handover](ufor.md), [instrument format](../doc/sample-format.md) | Definitions, preparation, and lifecycle cases implemented in uFor |
| Both sound engines | [enge handover](enge.md), [enge README](../../enge/README.md), [execution plan](../../enge/plan/engine-execution.md) | Shared synth reference exists; sampler and further backend work belong to enge |
| recs instrument hosting | [Playback boundary and acceptance](sample-playback.md) | Host integration remains separate work |
| Further sample-format features | [Format inventory](sample-format.md) | Explicit additions require design and approval |
| SFZ support and limits | [SFZ plan](sfz.md), [instrument format](../doc/sample-format.md) | Implemented bounded conversion profile; unsupported features are diagnosed |
| Physical checks | [Human verification](human.md) | Not established by unit tests |

## Broader design references

These long documents retain implemented profiles next to proposals and history.
They are reference material, not ordered task queues. Their titles and opening
navigation explain that distinction; filenames stay stable for existing links.

- [Architecture roadmap, checkpoints, and verification](master/verification-procedures.md):
  shared-model rationale, migration evidence, and acceptance discipline.
- [Cross-domain proposals and implemented profiles](master/future-proposals.md):
  controls, sequences, arrangements, bindings, slideshows, lighting, and broadcasts.
  A portable schema does not imply an application player exists.
- [Musical-model inventory and remaining decisions](master/deferred-work.md):
  instruments, modulation, DSP, and tuning; engine execution belongs to enge.
- [Archive policy](master/complete/README.md): finished work is identified by
  contract and checkpoint, not by moving mixed-status reference documents.

## Canonical packaging metadata

`pyproject.toml` uses `[project]` as its single package identity/version source,
Hatchling as its build backend, and uv for environment/lock management. There is
no parallel Poetry metadata. This cleanup changes no dependency versions.

## Additional work beyond the prompt

None.
