# Daily session directories

## Goal

Group capture sessions by their local calendar day. A session remains the
portable directory containing `session-record.jsonl`, `recording.toml`, and
media, but its default location becomes:

```text
<output root>/2006/09/14/20-15-15/
```

The `2006/09/14` directory is a day container and may contain several session
directories. The final `20-15-15` directory is one session. A collision at the
same second uses `20-15-15_1`, then `_2`, without overwriting an existing
session.

## Implementation

1. Replace the current single `YYYY-MM-DD HH-MM-SS` session-name construction
   with a local-date parent (`YYYY/MM/DD`) and time-only session leaf
   (`HH-MM-SS`). Apply it after expanding the configured output-directory
   pattern, so that option remains the root for generated sessions.
2. Preserve the session-directory contract: journals, media paths,
   `recording.toml`, `new_session`, and replacement-volume continuations all
   use the time-leaf directory. The day container has no journal or recording
   document of its own.
3. Keep reading existing flat timestamped session directories. Recovery and
   session browsing must continue to discover journals recursively, regardless
   of whether they occur directly below the output root or below a day
   container.
4. Update user documentation, protocol examples, test fixtures, and test
   helpers that recognize or remove generated session-directory components.

## Acceptance

- Two recordings on 14 September create distinct children of one
  `2006/09/14` directory; a recording after local midnight uses
  `2006/09/15`.
- `new_session` creates another time-leaf directory on the appropriate day and
  continues to link the two journals correctly.
- Card replacement retains the existing continuation semantics while using the
  new layout on the destination volume.
- Explicit output-directory time patterns are expanded before the day/session
  hierarchy is appended.
- Existing flat sessions remain browseable, recoverable, finalizable, and
  editable.

## Additional work beyond the prompt

None.
