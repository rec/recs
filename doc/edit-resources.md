# Edit resource planning

Use the existing `--dry-run` option to inspect work before rendering:

```console
recs edit clip /path/to/session/recording.toml --dry-run --scratch-directory /Volumes/Work/scratch
recs edit compose composition.toml /path/to/session/recording.toml --dry-run
```

Ordinary edit previews print the canonical score TOML with resource information
in comments. Composition previews report stages and resources. Both use score
metadata and the existing graph validator without decoding or allocating the
source timeline. Nested arrangements are planned recursively, not rendered.
Direct audio inputs still require header inspection and hashing to describe the
input; sealed recording metadata can be planned without reading audio payloads.
Full media integrity and audio-header checks remain part of actual rendering.

## Estimates

- Output frame counts come from validated graph extents, including silent gaps.
- Source and intermediate scratch estimates use float32: four bytes per frame per
  channel. They count full logical extents, without sparse-file savings.
- Composition totals conservatively count all stages as simultaneously live and
  may count shared source or prepared views more than once. They are not a precise
  measurement of peak allocated disk blocks.
- Audio-buffer RAM uses the renderer's bounded-block estimate, separate from
  scratch disk. Python objects, score metadata, and codec allocations are excluded.
- PCM/float WAV output estimates use sample width plus a 4096-byte per-file
  allowance. Session metadata is excluded. Compressed output sizes are unknown;
  a separate known-output subtotal still contributes to space checks.
- Calibration intervals, output lengths, and analysis memory require audio
  analysis. A composition containing calibration reports that stage and all
  subsequent estimates as unknown. Earlier stage estimates remain available;
  later selector and graph validation occurs during execution.

Unknown means unestimated, not zero or safe to fit. Resource planning is not an
integrity check or a guarantee that the invocation will succeed.

## Scratch placement and checks

`--scratch-directory PATH` applies to that edit invocation, including nested
arrangements and calibration. The directory must already exist. Without it,
the system temporary directory is used. The choice is not saved in capture
configuration or the edit recipe.

Before materialization, recs checks known scratch and destination requirements.
If both paths are on the same filesystem, their requirements are added together.
Each scratch allocation also checks its logical size against then-available
space. These conservative checks may reject a sparse edit that could fit through
filesystem-specific sparse allocation; recs does not assume that saving.

Checks reserve no capacity. Other processes, compressed output sizes, metadata,
and failures after a check can still exhaust storage. Existing error handling
remains active: failed preparation produces no completed output recording;
an interrupted output write leaves an unfinished journal rather than a sealed
session. Scratch files follow the existing prepared-audio object lifetime.
