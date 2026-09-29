# Recs follow-ups discovered during reccy work

These are recs-owned follow-ups. The shared primitives already exist in
reccy; each migration must preserve recs-specific policy and be verified in
recs. This list does not authorize a change to another repository.

## Validated configuration edits

`Cfg.set_attr` in `recs/cfg/cfg.py` still edits a revalidation dump directly.
Consider replacing the edit with `reccy.configuration.update.validated_update`.
Keep recs' mutable-address allowlist and address syntax. Test nested edits,
cross-field rejection, unchanged originals after failure, and authored units.

## Event-client closure in watch

`watch()` in `recs/daemon/watch.py` waits on its own completion event, which a
disconnected event stream may never set. Use `EventClient.wait_closed()` and
`terminal_reason` to wake on EOF or failure while preserving snapshot and
stop behavior. This does not provide an atomic snapshot/event handoff or
justify replaying control commands.

## Settings ownership claim

`claim_settings` and `release_settings` in `recs/daemon/instances.py` still
use an exclusive-create PID file and stale-file reclamation. Consider moving
the local ownership guard to `reccy.runtime.claims.ResourceClaim`, retaining
recs' settings-path identity, instance discovery, and user-facing conflict
policy. Choose a stable lock path and coordinate rollout so old and new claim
schemes cannot both own the same settings path. Test contention and recovery
with separate processes.

## Additional work beyond the prompt

None.
