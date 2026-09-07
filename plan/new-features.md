# Top Remaining Features

## Scope

This is the ranked product backlog for the five most valuable unfinished Recs
features. Completed work and ideas superseded by Showco or existing Recs tools
have been removed.

## 1. SFZ Export

Implement deterministic best-effort serialization from recsam to SFZ, with
complete diagnostics for fields that SFZ cannot represent. A completely
imported SFZ file must survive recsam-to-SFZ-to-recsam conversion without losing
supported behavior or Recs metadata.

The detailed design and acceptance criteria are in [SFZ Export](sfz-write.md).
This closes the interoperability loop for existing sample libraries and makes
recsam safer to adopt as an editable intermediate format.

## 2. Offline Recsam Playback

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
