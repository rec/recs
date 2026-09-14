# Handover

Recs is pinned to the Ufor revision that provides inline-score automation. The
edit package has been migrated from Ufor's retired arrangement-local automation
API, and generated crossfades are persisted as inline automation scores.

The main unresolved implementation boundary is Recs control-rate conversion:
the first migration should accept only inline automation that shares the audio
arrangement's exact rate. General rate conversion should wait for a dedicated
renderer design and tests.
