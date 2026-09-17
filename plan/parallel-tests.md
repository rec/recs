# Parallel unit tests

## Goal

Run the complete unit-test suite concurrently without changing what it proves,
sharing machine audio devices, or making tests order-dependent. The normal
developer command should reduce wall-clock time; `-n 0` remains available for
single-process debugging.

## Current safety assessment

The suite is suitable for process parallelism as written:

- Each test receives a pytest `tmp_path`. The autouse `instance_home` fixture
  derives its temporary `HOME` from that path, so workers do not share recs
  instance state.
- The autouse MIDI fixture and the `mock_devices`, `mock_mp`, and
  `mock_input_streams` fixtures replace hardware and multiprocessing access.
- The recorder subdirectory changes into its own `tmp_path` before each test.
- Audio, edit, recording, and SFZ fixtures are local temporary files or
  checked-in read-only fixtures.

This assessment covers unit tests only. Human device checks remain separate and
must not be added to the parallel command.

## Implementation

1. Add unpinned `pytest-xdist` to the development dependency group and refresh
   `uv.lock` in its own dependency commit.
2. Add a pytest configuration that makes the standard command:

   ```console
   uv run pytest -n auto --dist=worksteal
   ```

   `-n auto` selects the host's physical CPU count. `worksteal` starts with an
   even allocation and rebalances slow tests, which is appropriate for the
   uneven runtime and recording test modules. Do not hard-code a worker count:
   a developer may use `-n 0` for debugging or an explicit `-n N` when the
   machine is busy.
3. Keep pytest output capture enabled. xdist cannot provide ordinary live
   `-s` output; use a focused single-process test when interactive output is
   needed.
4. Run the full suite serially and in parallel at least three times. Record
   wall-clock time and confirm identical collection and pass counts.
5. If a parallel failure exposes shared mutable state, fix the owning fixture
   to isolate it. Use `pytest.mark.xdist_group` only for a real shared resource;
   do not serialise a whole directory merely because it contains a slow test.

## Acceptance

- `uv run pytest -n auto --dist=worksteal` passes repeatedly with the same test
  count as `uv run pytest -n 0`.
- No test opens a physical audio or MIDI device, uses the real home directory,
  or writes outside its pytest temporary directory while running in parallel.
- The parallel command has a materially lower wall-clock time than the measured
  serial baseline on the same machine.
- The existing focused-test workflow remains usable with `-n 0`.

## References

pytest-xdist documents automatic worker selection, `-n 0`, and the
`worksteal` distribution mode at
<https://pytest-xdist.readthedocs.io/en/stable/distribution.html>.

## Additional work beyond the prompt

None.
