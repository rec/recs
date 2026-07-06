# fmix evaluation

## Summary

I scanned the core `fmix` package, especially `fmix/fmix.py`,
`fmix/render.py`, and `fmix/audio_file.py`. I did not modify the project.
The issues below are behavior risks found by code inspection.

## Findings

### High: files with different sample rates are mixed without resampling

`FMix._samplerate_data()` reads each input file, takes the maximum sample rate,
and returns the raw arrays unchanged (`fmix/fmix.py:113-118`). `render_samples()`
then treats every array as though it used that selected sample rate.

If one input is 44.1 kHz and another is 48 kHz, their sample indexes no longer
refer to the same times. The result will drift or cut at the wrong positions.
This is a correctness defect for a mixer.

### High: rendering can produce the wrong slice when the first edit point is not zero

`render_samples()` builds an output array of length
`sample_ends[-1] - sample_ends[0]` (`fmix/render.py:20-22`) but later writes
into it using absolute input sample indexes (`fmix/render.py:24-45`). If the
first edit point starts after zero, `result[begin:end + F]` is offset too far
into the shorter output buffer.

This can produce leading silence, truncated segments, or empty writes depending
on the edit-point times.

### Medium: empty edit-point lists crash at render time

`render_samples()` indexes `sample_ends[-1]` and `sample_ends[0]`
(`fmix/render.py:20`) without validating that `f.edit_points` is non-empty.
`FMix` defaults `edit_points` to an empty list, so a minimal invocation can make
it through configuration and fail during rendering with an `IndexError`.

### Medium: ffmpeg conversion failures are ignored

For formats not handled directly by `soundfile`, `_read_write()` shells out to
`ffmpeg` (`fmix/audio_file.py:52-64`) but does not pass `check=True` or inspect
the return code. If `ffmpeg` is missing or conversion fails, the code proceeds
to read or write the expected temp file, producing a less helpful downstream
error or silently leaving a missing/invalid output.

### Low: channel counting depends on array rank rather than channel size

`FMix.channels` returns `max(len(d.shape) for d in self.data.values())`
(`fmix/fmix.py:74-76`). This works for the current convention where mono arrays
are rank 1 and stereo arrays are rank 2, but it reports rank, not channel
count. It would misreport multi-channel arrays with shape `(frames, 6)` as `2`.
