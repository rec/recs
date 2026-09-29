# recs issue audit

This began as a source and test audit on 2026-09-29, not a runtime or hardware validation. Resolved issues have been removed; original issue numbers are retained for reference. Locations below refer to the code at the time of the audit. "Confirmed" means the behavior follows directly from the cited code; "risk" means the failure needs a particular scheduling, I/O, or external-device condition. Priorities reflect potential data loss and whether a normal user can encounter the condition. Existing tests often cover the happy path; a suggested test is a missing *failure-mode* test, not a claim that the whole module is untested.

## P2: errors, APIs, maintenance, and performance

30. **Some failure paths still lack end-to-end tests.** The tree has dedicated tests for audio, config, daemon, edit, MIDI, OSC, recording, and runtime; it is not generally untested. A remaining high-value scenario is a complete final session document after more than 512 durable source-file events. Existing broad integration/regression tests should remain distinct from hardware validation.

## Additional work beyond the prompt

None.
