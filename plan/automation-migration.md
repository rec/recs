# Automation migration

## Goal

Move Recs audio-edit automation from Ufor's removed arrangement-local
`body.automation` list to inline `AutomationScore` parts placed by
`body.control_clips`. Preserve the existing route-gain crossfade waveform and
make every generated edit self-contained.

## Format change

An arrangement part may now contain a complete inline Ufor score. Recs uses this
only for generated private automation parts. Recording inputs and user-authored,
reusable definitions remain score references.

For a two-route crossfade, generate two inline parts. Each exports `control`,
has a direct gain curve with `equal_power` interpolation, and targets one route
gain. Add one control clip per part at timeline zero, with its source interval
equal to the requested crossfade duration.

The first curve starts at the route's configured gain and ends at zero. The
second starts at zero and ends at its configured gain. The renderer applies the
automation score's declared default before its first knot, then its curve value.

## Recs implementation

1. Pin Ufor to the commit containing `AutomationScore`, arrangement gain targets,
   equal-power gain curves, and inline part scores.
2. Replace imports of `AutomationPoint`, `AutomationSpec`, and the old
   arrangement interpolation enum with Ufor automation types.
3. Change `recs edit mix --crossfade` to add inline automation parts and control
   clips. It must write no auxiliary score files.
4. Update `Renderer` to collect inline automation scores from its arrangement
   parts, resolve each control clip, and evaluate the score at each requested
   timeline frame. Recs' audio renderer supports only exact same-rate control
   clips in this migration; reject other rates clearly until rate conversion is
   implemented there.
5. Remove the old static automation handling from the partial edit schema and
   renderer. Do not retain an adapter for `body.automation`.
6. Update direct and nested preparation so inline score parts require no file
   loading. Composition stages carry them inside their arrangement TOML.
7. Convert complete-arrangement fixtures, documentation examples, and tests from
   `body.automation` to inline automation parts and `body.control_clips`.

## Verification

- Ufor validates and round-trips an arrangement containing inline automation.
- Recs generates two inline control parts for `--crossfade` and no extra files in
  the invoking directory.
- The equal-power crossfade samples match the existing regression values.
- A saved edit TOML can be loaded and rendered after its original working
  directory is unavailable.
- A composition stage containing a crossfade remains replayable from its stored
  canonical TOML.
- The full Recs suite passes on the new Ufor revision.

## Commit order

First commit the Recs migration and its test/fixture/documentation updates.
Commit the Ufor pin and lockfile separately, after the new Ufor revision is
published. Each commit is pushed.

## Additional work beyond the prompt

None.
