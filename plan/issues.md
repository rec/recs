# recs issue audit

This began as a source and test audit on 2026-09-29, not a runtime or hardware validation. Resolved issues have been removed; original issue numbers are retained for reference. Locations below refer to the code at the time of the audit. "Confirmed" means the behavior follows directly from the cited code; "risk" means the failure needs a particular scheduling, I/O, or external-device condition. Priorities reflect potential data loss and whether a normal user can encounter the condition. Existing tests often cover the happy path; a suggested test is a missing *failure-mode* test, not a claim that the whole module is untested.

## P2: errors, APIs, maintenance, and performance

26. **`play` failure can leave recording paused (risk).** `PlaybackControl.play` pauses capture before constructing/starting the playback worker and has no cleanup if `PlaybackRunner.start` fails ([recs/runtime/playback_control.py:64](../recs/runtime/playback_control.py#L64)). Thread/process resource exhaustion can leave `resume_after_playback` set and the recording paused with no running playback. Make start failure restore capture and close the timeline.

27. **A few names hide different operations (API trap).** The playback API uses negative `session` values (`len(paths) + request.session`) while the field itself is not named `relative_session` ([recs/runtime/playback_control.py:45](../recs/runtime/playback_control.py#L45)); `stop` means stop playback in that component but stop the recorder elsewhere; `project use` versus `project switch` also encode start-versus-live semantics only in help. Prefer explicit names/help and errors over silently accepting misleading indices. This is a documentation/API review item, not a call for a broad rename.

28. **Large orchestration files concentrate unrelated failure modes.** `recs/runtime/recorder.py` (~1,060 lines) combines session lifecycle, device polling, IPC, card replacement, disk policy, playback, warnings, and project switching; `recs/edit/commands.py` (~721) handles command discovery, parsing, and arrangement generation; `recs/recording/baccy_import.py` (~697) handles import mapping and persistence. These are review and change-risk hotspots, particularly the recorder's interleaved cleanup paths. Extract only a cohesive responsibility when fixing a concrete issue; a size-only split would add navigation without removing coupling.

29. **Tiny files are not automatically a problem.** `recs/audio/header_size.py` is ~16 lines and called from one production module, so it could be inlined when next touched. `recs/daemon/gui_backend.py` is similarly small but provides an OS-specific IPC boundary used by tests; `recs/base/app_command.py` has several callers. There is no compelling immediate cleanup here.

30. **Some failure paths still lack end-to-end tests.** The tree has dedicated tests for audio, config, daemon, edit, MIDI, OSC, recording, and runtime; it is not generally untested. A remaining high-value scenario is a complete final session document after more than 512 durable source-file events. Existing broad integration/regression tests should remain distinct from hardware validation.

## Additional work beyond the prompt

None.
