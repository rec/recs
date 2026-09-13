# Control-clip persistence

## Goal

Generated Recs edits must retain the automation scores used by their
`control_clips`. A saved arrangement must never depend on a temporary file in
the caller's working directory.

## Ownership

`commands` creates immutable Ufor `AutomationScore` values for generated
crossfades. It does not write files. It returns those values with the generated
arrangement as a small authored-score collection.

The collection owns every generated score by its canonical TOML digest. Its
portable path is `definitions/<score-name>-<first-16-sha256>.toml`. Identical
scores share one entry. Parts in the arrangement refer to that path.

Recording definitions remain as they are today: imported recordings are external
score references and are rebased when an edit session is saved. Only generated
control scores belong to the edit-session definition collection.

## Direct edit flow

1. Generate the arrangement and its in-memory control-score collection.
2. Resolve both recording sources and control scores from memory, before any
   output directory is created.
3. At session creation, write each collection entry below `definitions/`, then
   write canonical `edit.toml` whose relative score references resolve from the
   new session directory.
4. Write the rendered media and recording metadata as usual.

The collection is written before `edit.toml`; a write failure therefore cannot
leave an edit score that points at absent generated definitions.

## Dry runs

Dry runs carry the same in-memory collection through preparation and print the
canonical `edit.toml`. They create neither `definitions/` nor any temporary
automation TOML files. The printed paths show exactly where a real output session
will store the definitions.

## Composition stages

`ResolvedStage` stores the generated definition collection alongside its
canonical arrangement, keyed by portable relative path and TOML text. Replaying a
composition reconstructs every stage without command discovery or files left by
an earlier run. During execution, each stage resolves its collection in memory;
only the final output session writes its collection to disk.

This keeps intermediate automation data visible in the replayable composition
artifact while avoiding unreferenced files beside the composition source.

## Verification

- Generated two-route crossfade produces two control-score entries, both with
  equal-power direct gain curves and route-gain targets.
- A direct edit renders the existing crossfade waveform and leaves no new file
  in its invoking directory.
- A saved output contains `edit.toml` and the referenced definition files; it
  can be loaded and rendered after the invoking directory is unavailable.
- Dry run writes nothing and still validates every control-clip reference.
- A composition with a generated crossfade records the stage collection and
  replays from that canonical composition without command discovery.

## Additional work beyond the prompt

None.
