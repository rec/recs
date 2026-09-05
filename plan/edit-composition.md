# Composite Edits

## Goal

Define a new edit that composes zero or more existing edits in declaration
order. A composite edit treats each child as a session transformation: the
first child consumes the composite input session, and every later child
consumes the session produced by the preceding child.

For edits `a`, `b`, and `c`:

```text
compose(a, b, c)(input) = c(b(a(input)))
```

The design must reuse the existing command resolver and session-producing edit
executor. It must not add a second renderer, merge unrelated arrangement
graphs, or treat recipe inheritance as composition.

## Semantics

Composition is ordered and sequential. TOML declaration order is execution
order.

- One child behaves exactly like invoking that edit directly.
- Several children produce one intermediate session per child.
- The result is the final child's `session-record.jsonl`.
- Zero children is the identity edit: its result is the original input session
  record.
- A child never mutates or appends to its input session.
- A failure stops the sequence. Completed child sessions remain intact and the
  next child is not started.

Do not render all children into one arrangement in the initial implementation.
That optimization is not valid in general: future MIDI, OSC, and user-defined
edits may have different execution models, and an edit may intentionally use an
encoding or media transformation that becomes the next edit's input.

Sequential execution means intermediate audio is encoded and decoded between
children. Lossy intermediate formats therefore cause generational loss. Recs
must show every intermediate format in its dry-run output and must not silently
replace a requested format. Users who intend further audio processing should
choose WAV, FLAC, or another suitable lossless intermediate format.

## Relationship To Existing Concepts

`extends` remains recipe inheritance. It resolves one command by overlaying
configuration before that command executes. It does not run the parent and
child as separate edits.

A composite edit instead invokes several fully independent commands. Each child
gets a new session ID, canonical `edit.toml`, generated media, and
`session-record.jsonl` through the existing execution path.

An explicit complete arrangement is not initially a valid child. A complete
`EditSpec` names its own source records and therefore does not necessarily
consume the preceding session. Composite children must resolve to command
recipes with `_command.operation`, so Recs can supply the current input record
unambiguously.

## TOML Format

Use a separate versioned `CompositionEdit` data class rather than adding
composition fields to `EditSpec`. `EditSpec` remains the complete arrangement
consumed by one renderer; `CompositionEdit` is orchestration over several such
executions.

```toml
schema_version = 1
kind = "composition"

[[edits]]
command = "clip"
start = 12.5
end = 48.0
channel = ["X18:1-2", "X18:3-4"]
format = "flac"
subtype = "pcm_24"

[[edits]]
command = "mix"
channel = ["edit:x18-1-2", "edit:x18-3-4"]
route_gain = [1.0, 0.5]
format = "flac"
subtype = "pcm_24"
```

`CompositionEdit` contains:

- `schema_version: Literal[1]`
- `kind: Literal['composition']`
- `edits: list[CompositionStep]`, defaulting to an empty list

`CompositionStep` contains:

- `command: str`, interpreted through the existing named-command or explicit
  TOML path resolver
- The reusable command options currently held by `EditCli`: `channel`, `start`,
  `end`, `interval`, `format`, `subtype`, `normalize`, `gain`, `route_gain`, and
  `crossfade`

It does not contain `record`, `destination`, or `dry_run`. The composition owns
the initial record and destination, supplies each later record itself, and
controls whether the whole operation is executed.

Extract the reusable option fields into one frozen Pydantic data class used by
both `EditCli` and `CompositionStep`. Do not maintain duplicate lists of edit
options or pass untyped CLI argument strings through the composition file.

Unknown fields, versions, and kinds fail during parsing. Empty command names and
explicit child paths that do not exist fail during resolution.

## Paths And Command Resolution

Resolve relative child command paths from the directory containing the
composition TOML. Named commands continue to use the current project, user, and
packaged command discovery order.

Resolve every child command before creating an output directory. Reject command
name collisions, inheritance cycles, missing files, and children that resolve
to complete arrangements during this preflight pass.

Copy the fully resolved composition to `edit.toml` at the root of the composite
output directory. Its child `command` values should be canonical paths relative
to that file where possible. Named commands must not remain dependent on later
changes to user or packaged recipes: record the resolved command source and its
effective options in the canonical composition.

Each child session also retains its existing canonical `edit.toml`. Those files
describe the exact arrangements rendered by each individual step; the root
composition file describes why and in what order those steps were run.

## Output Layout

A non-empty composition creates one container directory supplied or derived by
the CLI. Each child writes its ordinary session into a numbered subdirectory:

```text
2026-09-05 18-30-00 edit/
  edit.toml
  001-clip/
    edit.toml
    session-record.jsonl
    audio/
      ...
  002-mix/
    edit.toml
    session-record.jsonl
    audio/
      ...
```

Use a legal path component derived from the command name, prefixed by a
one-based, zero-padded sequence number. Numbering makes execution order stable
even when the same edit appears more than once.

The container is not itself a media session and therefore has no synthetic
`session-record.jsonl`. Its result is the final child's session record. Do not
duplicate the final child's file entries into an aggregate record.

A zero-child composition returns its input record without creating the
destination directory. This is the mathematical identity and avoids copying or
re-encoding an arbitrarily large session merely to manufacture a new identity.
Reject an explicit `--destination` for an empty composition because no output is
created there.

## Making Edited Sessions Composable

Before composition can feed one edit into another, sessions emitted by
`recs edit` must be valid inputs to the existing source resolver. Generated
`file_started` and `file_finished` entries currently need a stable `source` and
`track_name` pair that later selectors can address.

Use one documented generated source name, initially `edit`. Preserve each
output's stable ID as its track name. Record sufficient channel metadata for the
same selectors accepted from recorded sessions:

```text
edit:OUTPUT_ID[:OFFSET]
```

Do this for every ordinary edit, not only sessions created inside a
composition. A user must be able to feed any completed edit session into a
later standalone edit and get the same behavior.

The next child defaults to all compatible finished tracks in the preceding
session, using the existing command-generation rules. Explicit `channel`
selectors constrain that set normally.

## CLI

Add a packaged `compose` edit command or recognize a composition TOML through
the existing `recs edit PATH.toml` entry point:

```text
recs edit compose COMPOSITION.toml [RECORD]
recs edit COMPOSITION.toml [RECORD]
```

When `RECORD` is omitted, use the existing latest-session lookup. Do not perform
that lookup separately for each child.

`--destination` names the composition container, not an individual child
session. `--dry-run` resolves every child without creating directories and
prints:

- The initial input record.
- Every child command and resolved command file.
- The numbered destination of every child.
- Explicit or default selectors.
- Intermediate formats and subtypes.
- The final result record path.

Keep primitive edit invocation unchanged. Do not add composition-only options
to every ordinary command's help.

## Execution Architecture

Add a small `recs/edit/composition.py` module responsible for:

- Parsing and validating `CompositionEdit`.
- Resolving all child commands before output creation.
- Deriving contained child destinations.
- Calling the existing command completion and session execution functions for
  each child.
- Passing each completed child record to the next child.
- Returning the input record for zero children or the final child record
  otherwise.

Extract one public operation from the current CLI flow that executes a resolved
command from typed options, an input record, and a destination. Both the CLI and
composition executor should call it. Do not invoke the Recs CLI recursively or
construct subprocess commands.

Keep arrangement validation, rendering, output encoding, and session-record
writing in their current modules. Composition must not know how to process
audio blocks or write individual media files.

## Validation And Failure Handling

- Validate the complete composition and resolve all command files before
  creating the container.
- Reject a destination that already exists before running the first child.
- Require every child destination to remain inside the container.
- Reject a child that does not consume the supplied record.
- Reject a later child selector that cannot resolve against the preceding
  session before creating that child's directory.
- Stop on the first command, record-resolution, rendering, or write failure.
- Keep completed child sessions and any truthful incomplete child session for
  inspection and recovery.
- Do not run later children after a failure and do not delete completed output.
- Do not add rollback semantics.
- A zero-child composition still validates that its input record exists and is
  structurally readable before returning it.

The canonical root `edit.toml` may exist beside completed and incomplete child
directories after a failure. That file is the intended operation, while each
child session record states what actually completed.

## Tests

Use 48 kHz WAV fixtures of at least one second for digital-audio regression
tests. Assert public results, generated files, canonical TOML, and session
records rather than private helper calls.

1. Parse an empty composition and reject unknown versions, kinds, and fields.
2. Verify zero children returns the validated input record and creates no
   destination.
3. Reject `--destination` for a zero-child composition.
4. Execute one child and verify its behavior matches the same standalone edit.
5. Execute two children and verify the second reads the first child's session,
   not the original session.
6. Verify declaration order and stable numbered child directories, including
   repeated command names.
7. Verify generated edit records expose selectors of the form
   `edit:OUTPUT_ID[:OFFSET]` and can be used by a standalone later edit.
8. Verify omitted selectors choose compatible outputs from the immediately
   preceding session.
9. Resolve all child command files before creating the container and reject
   collisions, cycles, missing paths, and complete arrangements as children.
10. Verify child paths are relative to the composition file and child output
    directories cannot escape the container.
11. Verify dry-run prints every stage and performs no writes.
12. Fail the second child and verify the first session remains complete, the
    second remains truthfully incomplete when writing began, and no third child
    starts.
13. Verify canonical root TOML records resolved child definitions and effective
    typed options without executable command strings.
14. Verify a lossy intermediate format is preserved and reported rather than
    silently replaced.
15. Verify existing primitive edit commands and recipe inheritance retain their
    current behavior.

## Implementation Order

1. Make ordinary edited sessions valid inputs to later edits by recording a
   stable generated source and output track identity; add standalone chaining
   tests first.
2. Extract the shared frozen command-options data class and a typed operation
   for executing one resolved command without going through CLI parsing.
3. Add `CompositionStep`, `CompositionEdit`, TOML parsing, canonical writing,
   and full preflight resolution.
4. Implement zero-child identity behavior and dry-run reporting.
5. Implement contained sequential child execution and final-record return.
6. Add the `compose` command and explicit composition-file dispatch to the CLI.
7. Run the focused edit tests, the complete Recs suite, formatting, linting,
   type checking, and pyupgrade.

## Acceptance Criteria

- A composition contains any number of existing command edits, including zero.
- Children execute left to right and each consumes the preceding output
  session.
- Zero children returns the original record without copying media.
- Every non-empty child uses the existing edit renderer and emits an ordinary,
  independently inspectable session.
- The composite container has deterministic child paths and one canonical root
  `edit.toml`.
- Completed and failed work remains truthfully represented without rollback.
- Edited sessions are valid inputs to both composed and standalone later edits.
- Recipe inheritance and composition remain distinct concepts.
- Composition introduces no Python plugins, shell commands, subprocess CLI
  recursion, or media-specific renderer path.

## Additional Work Beyond The Prompt

None.
