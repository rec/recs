# Active plans and ownership

Use [the README](../README.md) and [project documentation](../doc/) for
implemented recs behavior. Plans contain only unresolved work and proposals;
completed plans remain recoverable in Git history. Proposals do not authorize
implementation by themselves.

## recs work

None. SFZ work now belongs to [safaz](https://github.com/rec/safaz/blob/main/plan/sfz.md).

## Remaining proposals

- [Cross-domain proposals](master/future-proposals.md)
- [Musical-model decisions](master/deferred-work.md)

## Owning projects

- [uFor documentation](../../ufor/doc/api-map.md) owns portable models and
  implemented reference semantics. Its [asset-location](../../ufor/plan/url-paths.md)
  and [cache](../../ufor/plan/asset-cache.md) plans track remaining host work.
- [enge's roadmap](../../enge/plan/roadmap.md) owns engine sequencing; its
  [execution plan](../../enge/plan/engine-execution.md) tracks control and live
  execution integration.
- [safaz's plan](../../safaz/plan/sfz.md) owns remaining SFZ conversion work.

Read the owning project's current documentation before implementing an extension.
Do not repeat completed model migrations or maintain competing engine checklists
in recs.

## Additional work beyond the prompt

None.
