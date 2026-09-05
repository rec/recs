# Unit Provenance

## Goal

Preserve an explicitly authored unit string such as `250ms` while applications
continue to calculate with normalized `float` and `int` values. Put the generic
implementation in Reccy; keep Recs-specific persistence policy in Recs.

## Reccy Design

1. Move the shared Pint registry, unit annotations, and Tyro constructor support
   into `reccy.units`.
2. Have a unit annotation return a lightweight numeric subclass for string input.
   It behaves as the normalized number and carries the exact authored text and
   canonical unit. Numeric input remains an ordinary number with no provenance.
   Pint `Quantity` objects do not escape validation.
3. Add a frozen `UnitProvenance` model containing `authored`, `normalized`, and
   `canonical_unit`, plus a collector keyed by dotted field path. List positions
   are represented by numeric path components.
4. Provide two explicit serializers:
   - Runtime serialization emits plain normalized numbers, matching current JSON,
     IPC, and arithmetic behavior.
   - Authored serialization substitutes the original string where provenance is
     still attached.
5. Provide a revalidation dump that preserves authored strings. Code that rebuilds
   a model, such as `Cfg.set_attr()`, uses this dump so changing one field does not
   discard provenance from every other field.

No global collector or validation context is used. Copying an authored numeric
value preserves provenance. Replacing it with a number drops provenance; replacing
it with another unit string creates new provenance. Arithmetic naturally returns
an ordinary number and therefore also drops provenance.

## Recs Integration

1. Replace `recs.base.units` and its Tyro adapters with imports from Reccy. Keep
   disk-threshold parsing and the legacy `m`-means-minutes rule in Recs.
2. Continue using runtime serialization for protocol replies, source-process
   messages, session records, and status data. These remain canonical numbers.
3. Use authored serialization only for saved settings. Thus `250ms` can survive a
   load/save cycle, while an API update using `0.25` is saved as a number.
4. Preserve provenance while merging CLI values, saved settings, and device
   profiles. The winning value also supplies the winning provenance.

Session-record `cfg_set` events deliberately remain normalized: they describe the
effective recording state, not the spelling used to request it.

## Verification

- Test equivalent units, exact spelling, numeric input, integer conversion, and
  wrong dimensions in Reccy.
- Test copy, arithmetic, model reconstruction, nested fields, lists, and runtime
  versus authored serialization.
- In Recs, test saved-settings round trips and precedence among CLI, API, profiles,
  and saved values. Confirm protocol and session-record output remains numeric.
- Run the full Reccy and Recs checks before committing each repository.

## Commit Order

1. Add provenance-aware unit values and serializers to Reccy.
2. Migrate Recs to Reccy units without changing persistence output.
3. Switch saved settings to authored serialization and add precedence tests.

## Additional Work Beyond The Prompt

None.
