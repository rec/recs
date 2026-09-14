# Handover

Recs is currently pinned to an older Ufor revision because its edit package still
uses Ufor's retired arrangement-local automation API. The Recs working tree is
clean apart from two user-owned recording directories and journals; do not stage
them.

Ufor's current main branch has the required automation and inline-score support,
and its full test suite passes. Recs must be migrated to that API before its
dependency pin can advance. The immediate work is described in
[`plan/automation-migration.md`](../plan/automation-migration.md).

The main unresolved implementation boundary is Recs control-rate conversion:
the first migration should accept only inline automation that shares the audio
arrangement's exact rate. General rate conversion should wait for a dedicated
renderer design and tests.
