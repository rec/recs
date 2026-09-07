# Top Remaining Features

## Scope

This is the ranked product backlog for the most valuable unfinished Recs
features. Completed work and ideas superseded by Showco or existing Recs tools
have been removed.

## 1. Offline Recsam Playback

Implement the recsam playback engine first as deterministic offline rendering
from performance events into a new Recs session. Establish slot selection,
voice lifecycle, timing, loops, envelopes, modulation, routing, and shared asset
loading before adding a live audio host.

The detailed design and hardware-validation boundary are in
[Sample Playback](sample-playback.md) and
[Human And Experimental Verification](human.md).

This turns recsam from a schema and converter into a usable instrument format
while keeping live latency and callback risk out of the first implementation.

## Additional Work Beyond The Prompt

None.
