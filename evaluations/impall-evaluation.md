# impall evaluation

## Summary

I scanned `impall/__init__.py` and the bundled tests. The project is small, so
this review covers the main runtime module. I did not modify the project.

## Findings

### High: warning filters are not restored safely

`ImpAllTest.impall()` calls `warnings.simplefilter()` and later removes
`warnings.filters[0]` with `warnings.filters.pop(0)` (`impall/__init__.py:179-188`).
If an imported module mutates warning filters, the code may pop the wrong filter
and leave global warning state changed for the rest of the test process.

This should preserve and restore the whole `warnings.filters` list, similar to
how `sys.path` is restored.

### Medium: `import_file()` can return a cached module from a previous path

`import_file()` temporarily prepends the computed root to `sys.path`, imports
the module, and restores `sys.path` (`impall/__init__.py:276-289`). It does not
clear or isolate `sys.modules`.

If a caller imports two different files that resolve to the same module path,
the second call can return the first cached module instead of loading the file
requested by the caller. This is especially likely in temp directories or tests
with repeated simple names such as `single.py`.

### Medium: `CLEAR_SYS_MODULES` does not fully isolate import side effects

The `_import()` path snapshots `sys.modules` and `sys.path`
(`impall/__init__.py:220-239`), but imported modules can still mutate existing
module objects, warning filters, logging handlers, environment variables, or
other process globals. The README says this reduces side effects, which is
accurate, but users may overread it as full isolation.

This is more of a feature-risk boundary than a bug, but it matters because
`impall` intentionally imports arbitrary project files.

### Low: module-pattern matching has unfinished identifier handling

`_split_pattern()` detects dot-separated identifier patterns but only has a
`pass  # TODO` branch before falling back to `fnmatch` (`impall/__init__.py:321-329`).
If the API intends `INCLUDE`/`EXCLUDE` to support module-style names as well as
paths, that branch is incomplete.

### Low: `path_to_import()` is cached across filesystem changes

`path_to_import()` is `lru_cache`d (`impall/__init__.py:247-273`). In normal
CLI use this is fine, but long-running test processes that create, remove, or
rename packages under the same path can get stale path-to-module results.
