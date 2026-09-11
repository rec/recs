# Live slideshow format

Part of the [master proposal](master.md). A slideshow is an ordered visual
performance: it can play automatically, be advanced by a person, react to a
cue, or mix those modes during one run. It is editable without opening an image
or video codec. Still images are its primary material; video clips are allowed
as visual assets. General video editing and codec implementation remain outside
this plan.

## The score

A slideshow score contains named visual assets, ordered items, optional
audio accompaniment, caption tracks, image descriptions, cues, and a default
run policy. Each item has a stable name. Its visual source is either an explicit
asset or a declared directory selection. A directory selection is resolved to
explicit items when it is imported or sealed, so later directory changes cannot
silently alter an authored show.

An item has a display interval in the slideshow timebase. A still image needs a
positive duration. A video clip selects a finite source interval and has a
declared playback speed of one in the first profile. Its embedded audio is mute
unless the score explicitly supplies it as an accompaniment source. This
keeps visual editing and audio accompaniment independent.

Visual placement declares a normalized crop rectangle, rotation in right-angle
steps, and a fit rule: `contain`, `cover`, or `stretch`. Cropping changes only
the item's view of the asset. A display binding chooses an actual screen,
projector, resolution, color conversion, and image/video decoder.

## Ordering and bulk selection

A bulk selection is an authoring instruction, not a vague filesystem lookup.
It names a relative directory, whether to recurse, inclusion and exclusion
patterns, and an ordering rule. The first profile supports `path` ordering by
Unicode code-point order of normalized relative paths. A later natural or
capture-time order needs its own specified comparator.

The selection resolves only regular files beneath the score root. It rejects
paths that escape the root through `..` or a symlink. Patterns apply to the
normalized relative path, use `/` as a separator, and do not match directories
by themselves. The resolved result records each source asset's path, byte
length, and SHA-256. An empty selection is an error unless it is explicitly
marked optional.

The selection may be followed by ordinary explicit items. This expresses
“play these directories, excluding these files and patterns, then finish with
these two images” without special end-of-show fields:

```toml
[[selections]]
name = "travel"
directory = "photos/travel"
recursive = true
include = ["**/*.jpg", "**/*.png"]
exclude = ["**/draft-*", "**/duplicate.jpg"]
order = "path"
duration = { seconds = 8 }

[[items]]
name = "closing-sunrise"
asset = "photos/finale/sunrise.jpg"
duration = { seconds = 12 }

[[items]]
name = "closing-map"
asset = "photos/finale/map.png"
duration = { seconds = 12 }
```

Resolving the selection creates one item per matching asset, in the declared
order, before `closing-sunrise` and `closing-map`. The author may then edit any
resolved item, move it, replace its crop, or remove it. The original selection
remains provenance and can be deliberately re-resolved as a new edit operation;
it never changes the existing order by itself.

## Transitions and timing

Each item starts after its predecessor's display interval, except where an
explicit transition overlaps them. A transition belongs to the boundary between
two named items and declares a nonnegative duration no longer than either
visible interval. The first profile has `cut`, `crossfade`, and directional
`wipe`; a host rejects an unsupported transition instead of substituting one.
A zero-duration transition is a cut.

Cues are typed events with a slideshow position and ordinal. They may mark a
slide, arm an operator action, or expose a named output for a binding. The
definition records no executable shell command, network request, or device
address. A binding decides whether a named cue controls lights, sound, a screen,
or an operator interface.

## Audio accompaniment and captions

An accompaniment is a separate audio source, such as a recording stream or
audio asset, with an explicit slideshow start position and finite source range.
It may begin before the first visual item or continue after the last one when
the requested render interval includes it. Visual advance never trims or seeks
the accompaniment unless the authored run policy says so.

Every audible accompaniment needs a caption track for the hearing-impaired.
A track declares language and contains ordered, non-overlapping timed captions
with text and optional speaker name. It may instead reference a sealed WebVTT,
TTML, IMSC, or EBU-TT asset when preserving a source format matters. Captions
use slideshow time, including an explicit offset from their audio source, so a
host does not guess synchronization from filename or duration.

```toml
[accompaniment]
asset = "audio/narration.flac"
start = { seconds = 0 }

[[captions]]
start = { seconds = 2 }
end = { seconds = 5 }
language = "en"
speaker = "Tom"
text = "The first train arrived before sunrise."
```

## Image descriptions

Every visual item has an authorable text description for visually impaired
audiences. `alt` is a concise identification suitable for immediate screen
reader output. `description` is an optional longer account. Both describe the
authored crop and item context, not merely the source filename. A video item
also provides a description of its visual action or refers to timed audio
description cues when that action changes during the clip.

Descriptions are part of the editable item. They are not generated from image
analysis, hidden in display-specific metadata, or replaced when an asset is
renamed. A host can present `alt` at item entry and make the longer description
available on demand without changing the visual timeline.

## Live performance and run records

The default policy is one of `automatic`, `manual`, or `cue`. Automatic items
advance at their scheduled boundary. Manual items hold until an explicit
operator advance. Cue items hold until their named cue occurs. The performer
may safely advance, go back, hold, jump to a named item, or temporarily take
manual control; each action is an observed run event.

A run record captures the resolved asset list and hashes, entered items,
transition starts, operator actions, delivered cues, caption presentation, and
display failures. Returning to an earlier item is an observable choice, not a
rewrite of the authored timeline. An as-presented replay follows recorded
decisions; a fresh performance follows the definition and current binding.

## Preparation and validation

Preparation verifies assets, resolves selections, validates transition bounds,
checks that all caption intervals are valid, and requires `alt` for every item.
It reports a video asset whose selected source interval or decoder is unsupported.
It does not decode media, connect a display, transmit cues, or claim that the
show can be realized on a particular machine.

The portable package holds image and video assets, audio accompaniment, caption
assets when used, the resolved slideshow definition, and optional run records.
Each dependency remains relative to the package root and sealed by byte length
and SHA-256. A missing optional visual may use a declared replacement item; a
missing required visual or accessible text is a preparation failure.

## What remains

This is a format plan. The next implementation work is a pure schema and
selection resolver with language-neutral cases for ordering, exclusions,
transitions, captions, descriptions, and recorded manual decisions. Image/video
decoding, screen output, cue delivery, caption rendering, and audio playback
belong to hosts and bindings. A later decision may add richer crops, animation,
multiple displays, live camera inputs, or new transition contracts.

## Additional work beyond the prompt

None.
