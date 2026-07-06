# tdir evaluation

## Summary

I scanned `tdir/__init__.py` and its tests. The library is intentionally small
and test-focused, but there are a few sharp edges around cleanup and path
handling. I did not modify the project.

## Findings

### High: temp directories can leak if setup fails

`_Tdir.__enter__()` creates the temp directory and then calls `fill()` before
the context manager is fully entered (`tdir/__init__.py:194-215`). If `fill()`
raises, Python will not call `_Tdir.__exit__()`, so the `TemporaryDirectory`
cleanup path is skipped.

This is easy to trigger with an unsupported fill value. The tests assert that
the error is raised, but they do not check whether the temporary directory was
removed after the failed `__enter__`.

### High: fill keys can escape the target root

`fill()` directly combines user-provided keys with the root path
(`tdir/__init__.py:240-260` and following). A key such as `"../outside"` writes
outside the requested root. That is surprising for a helper whose purpose is to
populate a temporary directory.

This may be acceptable for trusted tests, but it is a real footgun if callers
pass generated fixture names.

### Medium: `clear=True` can delete real directories when used with `use_dir`

`use_dir` deliberately uses a caller-provided directory and does not remove it
on exit (`tdir/__init__.py:157-160`, `tdir/__init__.py:194-200`). If combined
with `clear=True`, `_Tdir.__enter__()` deletes every child of that directory
(`tdir/__init__.py:202-207`).

That is documented only indirectly. Because `use_dir='.'` is shown as an
example in the docstring, `tdir(use_dir='.', clear=True)` is a potentially
destructive call.

### Medium: decorated functions reuse the same `_Tdir` object

The decorator closure constructs one `_Tdir` object and reuses it for every
call (`tdir/__init__.py:166-181`). Sequential tests are fine, but concurrent
invocations of the same decorated function share mutable attributes such as
`directory`, `_td`, and `old_directory`.

This makes decorated functions not thread-safe.

### Low: cleanup errors are printed but not surfaced

When restoring the working directory fails, `_Tdir.__exit__()` prints a
traceback and continues (`tdir/__init__.py:223-227`). That avoids masking a test
failure, but it can also let a process continue in an unknown current directory.
For a test helper, a hard failure may be safer.
