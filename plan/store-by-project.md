# Store sessions by project

## Goal

Place every generated session below a project directory. The generated layout
becomes:

```text
<output root>/<project name>/YYYY/MM/DD/HH-MM-SS/
```

Sessions in the default workspace use the reserved directory name
`-default-`:

```text
<output root>/-default-/YYYY/MM/DD/HH-MM-SS/
```

The time-named leaf remains the portable session directory. The project and
day directories are containers only.

## Implementation

1. Make the session-path constructor take the current optional `project_name`
   and insert either that name or `-default-` between the expanded output root
   and the existing `YYYY/MM/DD/HH-MM-SS` hierarchy. Keep collision suffixes
   on the time leaf.
2. Pass the active workspace project name when creating the initial session,
   a `new_session` continuation, a replacement-volume continuation, and a
   session after a mutable configuration change. Project switching already
   creates a new session, so its next capture must use the newly selected
   project directory.
3. Reserve `-default-` as a project name so a named project cannot share the
   default workspace's session directory.
4. Keep discovery, browsing, recovery, editing, export, and continuation
   links recursive and compatible with existing session locations. Do not move
   historical session directories.
5. Update the user-facing session-directory documentation, protocol examples,
   and focused tests for named, default, switched, and replacement sessions.

## Acceptance

- A default-workspace session is created below `-default-/YYYY/MM/DD/`.
- A named-project session is created below that project's directory.
- `new_session`, card replacement, and project switching preserve the active
  project directory while retaining their current continuation semantics.
- A project named `-default-` is rejected.
- Existing non-project-prefixed session directories remain readable.

## Additional work beyond the prompt

None.
