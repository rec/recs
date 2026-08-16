# Code quality evaluation

## Summary

The test suite passes, but the installed CLI entry point is broken and the MP3
conversion guard can never run. Format-specific size accounting also uses a
different format list from the file writers when an input file's format is
inherited. The required lint and type checks currently fail.

## Findings

### High: the installed `recs` command points to a missing module

`pyproject.toml:28` declares `recs = "recs.base.cli:run"`, but there is no
`recs/base/cli.py`. The actual `run()` function is in `recs/__main__.py:11`.
Consequently, package installation can succeed while the generated `recs`
console command fails during import.

### High: the MP3 float conversion guard is unreachable

`recs/ui/source_recorder.py:60` compares `self.cfg.formats`, a sequence of
formats, directly with `Format.mp3`, a single enum value. That comparison is
always false. The adjacent comment says float32 MP3 input crashes, so the
intended float64 conversion never protects that path.

### Medium: inherited output formats use the wrong size-accounting format

`recs/audio/channel_writer.py:69-72` correctly inherits the source format when
processing a file without an explicit format option and stores it in
`self.formats`. However, `recs/audio/channel_writer.py:103` calculates the file
size limit from `cfg.formats`, and `recs/audio/channel_writer.py:147` calculates
header size from `self.cfg.formats`. Both should describe the formats used by
the openers. For an inherited non-WAV format, the writer can apply WAV's size
limit and header estimate to a different file format.

### Medium: broad exception handling hides shutdown and recording failures

`recs/base/_query_device.py:12-17` catches `BaseException`, which includes
`KeyboardInterrupt` and `SystemExit`, and reports every failure as an empty
device list. `recs/cfg/file_source.py:42-59` catches every `Exception`, prints a
traceback, and stops the worker without propagating failure to the parent.
`recs/cfg/device.py:47-52` follows the same pattern inside the audio callback.
These paths can turn operational failures into normal-looking termination or
"no devices" results.

### Low: unused production code and stale compatibility aliases remain

- `recs/ui/source_recorder.py:16-18` defines `NEW_CODE_FLAG`, `FINISH`, and
  `OFFLINE_TIME`; none is referenced.
- `recs/misc/contexts.py:6` is not referenced by production or test code.
- `Counter` and `Accumulator` in `recs/misc/counter.py:18-56` are referenced
  only by their unit tests, while production uses `MovingBlock`.
- All three counter classes retain deprecated `__call__` aliases at
  `recs/misc/counter.py:27`, `:47`, and `:72`.

### Low: required static checks do not pass

`uv run ty check recs` reports 12 errors and 5 warnings. The errors include
incompatible Click method overrides, assignments inferred as incompatible
literals, and invalid numeric operations and return types in
`recs/misc/counter.py`.

`uv run ruff check --select B,E,F,I recs test` reports 16 errors: 14 `B008`
function-call defaults in the Typer command declaration, one `B904` exception
chaining issue in `recs/cfg/track.py`, and one `B015` pointless comparison in
`test/cfg/test_hash_cmp.py`.

## Verification

- `uv run pytest`: 174 passed.
- `uv run ty check recs`: failed with 17 diagnostics.
- `uv run ruff check --select B,E,F,I recs test`: failed with 16 errors.

The evaluation was static except for the repository's test, lint, and type-check
commands. Audio devices and the full recorder runtime were not exercised.
