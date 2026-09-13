# Multiple Recs instances

## Goal

Allow these processes to coexist for one user:

- zero or one Recs daemon;
- zero or more local Recs instances started from a command line or subprocess.

There is never more than one daemon. Additional instances are ordinary local
processes, not additional services or daemon variants.

Every instance can have different saved settings and can receive Recs protocol
requests. The command-line client makes the usual local instance the easiest one
to control while retaining an explicit route to the daemon.

## Compatibility rule

Nothing changes when the daemon is the only running Recs instance:

- `recs daemon install`, `start`, `stop`, `restart`, and `status` behave as they
  do now.
- The daemon uses the existing settings file.
- The daemon listens on the existing control and event endpoints.
- `recs control COMMAND` reaches the daemon.
- `recs watch` watches the daemon.
- Existing Python clients using `external_control_endpoint()` or
  `external_event_endpoint()` continue to reach the daemon.
- Existing protocol request and response shapes remain valid.

This compatibility path must not depend on instance discovery. When no local
instance is selected, clients continue to use the daemon's established fixed
endpoint directly.

## Process roles

### Daemon

The daemon remains a single, special process managed by the operating system. It
owns the existing fixed endpoints and current daemon settings. Starting another
daemon while it is running remains an error.

If a second process is accidentally started in daemon mode, it must fail before
opening recording devices. It must not continue as an uncontrolled recorder.

### Local instance

A local instance is any normal Recs recorder started from a command line or
subprocess. It does not require daemon installation or permission to install a
service. Any number may run concurrently, subject to audio-device and filesystem
constraints imposed by the host.

Every local instance starts a Recs protocol control server and event server. This
is part of an ordinary Recs run and does not turn it into a daemon. Its servers
exist only for the lifetime of that process.

## Saved settings

Use the existing named setup profiles for local instances that need persistent,
independent settings:

```sh
recs --profile second-interface
recs --profile location-recorder
```

The daemon continues to use the current unprofiled settings file at
`~/.config/recs/settings.json`.

A profiled local instance uses a mutable settings overlay belonging to that
profile, stored separately from the daemon and other profiles, for example:

```text
~/.config/recs/profile-settings/second-interface.json
```

Load settings in this order:

1. the named setup profile;
2. the profile's mutable settings overlay, if saving is enabled;
3. explicit command-line arguments.

Protocol changes to mutable settings are saved only to that instance's settings
destination. An unprofiled local process with saving disabled remains ephemeral.
An unprofiled process with `--save-settings` retains the existing global-settings
behavior.

Two live processes must not both write the same settings destination. Reject the
later save-enabled process before recording starts, naming the existing PID and
settings profile. Processes may read the same setup profile concurrently when at
most one of them saves changes.

## Local endpoints

Each local instance receives unique control and event endpoints. On Unix-like
systems, use:

```text
~/.local/state/recs/instances/<pid>-<start-token>/control.sock
~/.local/state/recs/instances/<pid>-<start-token>/events.sock
```

Use equivalent uniquely named pipes on Windows. The opaque start token prevents
stale state from an earlier process with the same reused PID from identifying a
new process.

The daemon does not move to this directory. It continues using:

```text
~/.local/state/recs/control.sock
~/.local/state/recs/events.sock
```

A local instance creates its endpoints before opening recording devices. Failure
to create them aborts that local startup, since otherwise the process could not be
selected or controlled as promised.

## Instance discovery

Each instance atomically publishes a small descriptor under
`~/.local/state/recs/instances/`. The daemon descriptor points to its fixed
endpoints; a local descriptor points to its unique endpoints. Use one descriptor
file per process so concurrent local startups never rewrite a shared registry.

Each descriptor contains:

- PID;
- opaque start token;
- precise wall-clock startup time;
- role: `daemon` or `local`;
- profile name, if any;
- control and event endpoints;
- Recs protocol version;
- a short display summary of selected input sources.

Publish the descriptor only after its endpoints accept connections. Remove it on
orderly shutdown. Discovery validates a candidate by connecting and comparing its
reported PID and start token with the descriptor. Ignore stale descriptors after
validation fails. Checking whether the PID exists is insufficient because PIDs
are reused.

Add PID, start token, role, profile, and startup time to status and capabilities.
These fields let a client verify the process reached through a descriptor. They do
not alter existing command semantics.

## Selecting an instance

Add target selection to `recs control` and `recs watch`:

```sh
recs control status
recs control --daemon status
recs control --instance 43120 status
recs control --instance -1 status
recs control --instance -2 pause

recs watch
recs watch --daemon
recs watch --instance 43120
```

The rules are:

| Selector | Target |
| --- | --- |
| no selector | Most recently started local instance; if none exists, the daemon |
| `--daemon` | The one daemon |
| `--instance PID` | The Recs process with that PID, whether daemon or local |
| `--instance -1` | Most recently started local instance |
| `--instance -2` | Second most recently started local instance |
| `--instance -3` | Third most recently started local instance |

Negative positions enumerate local instances only. The daemon never changes their
numbering. An unqualified command and `--instance -1` therefore reach the same
process whenever at least one local instance is running.

Zero is invalid. A positive PID must identify a discoverable Recs instance, not
merely any live operating-system process. `--daemon` fails clearly if no daemon is
running. An unavailable PID or negative position prints the live instance list
and sends no request.

This produces the required defaults:

- daemon only: use the daemon, exactly as today;
- one local only: use that local instance;
- daemon plus local: use the local instance;
- several locals: use the most recently started local instance;
- several locals plus daemon: use the most recently started local instance.

Use `--daemon`, a PID, or a negative position whenever the default is not the
desired process.

## Listing instances

Add:

```sh
recs control instances
```

This is a discovery operation and sends no request. Print a JSON array, newest
local instance first and the daemon separately identified. Each item contains the
PID, role, profile, startup time, selected sources, and whether it is the current
default.

The listing makes daemon-plus-local operation easy to inspect before sending a
mutating request. Keep the normal control-command response unchanged so existing
scripts still receive exactly the protocol result on standard output.

`recs daemon status` continues to describe only the daemon. It does not become an
all-instance command.

## Races and failure behavior

Resolve the selected target immediately before each CLI operation. Separate CLI
invocations do not cache a default.

After connecting through a descriptor, verify the returned PID and start token.
If that process exits between discovery and connection, report that it
disappeared. Never retry the request against a different process, even when the
original selection was implicit. A mutating request must not silently move from
one recorder to another.

Only one control request may be pending in each recorder, retaining the current
serialization rule. Different instances may handle requests concurrently.

Startup ordering uses the descriptor startup time, with PID and start token as a
stable tie-breaker. It never uses descriptor modification time, which can change
during cleanup or inspection.

## API boundaries

The current fixed endpoint functions continue to mean “the daemon endpoint.”
They must not begin returning whichever local instance happens to be newest.

Add a separate discovery API used by the command-line client. It returns verified
instance descriptors and resolves daemon, PID, and local-position selectors.
Other clients can opt into that API without changing existing daemon-oriented
clients.

Instance selection is outside the Recs request payload. The client chooses an
endpoint and then sends the same request it sends today. The recorder reports its
identity through status and capabilities, but ordinary requests do not acquire a
target field.

## Implementation sequence

### 1. Instance identity

Create a frozen identity model containing PID, start token, startup time, role,
and optional profile. Add it to status and capabilities without changing existing
fields.

Acceptance: identity round-trips through the protocol, and a daemon-only status
request otherwise matches current behavior.

### 2. Local protocol servers

Create unique local endpoint paths and start the existing external protocol server
for normal local recorder processes. Leave daemon endpoints unchanged. Make all
endpoint failures fatal before recording devices open.

Acceptance: a foreground Recs process answers `status`; the daemon continues to
answer on its established endpoint; and attempting a second daemon fails.

### 3. Discovery

Publish one atomic descriptor per ready process, remove it on shutdown, validate
identity on discovery, and ignore stale descriptors. Implement `recs control
instances`.

Acceptance: simultaneous local starts create separate valid descriptors; a crash
leaves only ignorable stale state; and PID reuse cannot select the wrong process.

### 4. CLI selection

Add `--daemon` and `--instance` to `control` and `watch`. Implement local-only
negative positions and the newest-local-then-daemon default.

Acceptance covers no instances, daemon only, one local, daemon plus local, several
locals, several locals plus daemon, daemon selection, PID selection, every valid
negative position, zero, out-of-range positions, stale records, and a selected
process exiting before connection.

### 5. Per-profile mutable settings

Add profile-specific mutable settings overlays while retaining the daemon's
existing global settings file. Enforce one live writer per settings destination.

Acceptance: modifying one profile affects no other profile or daemon; restarting
that profile restores its values; ephemeral instances write nothing; and a second
writer for one settings destination fails before recording starts.

### 6. Documentation and subprocess verification

Update the protocol, daemon, setup-profile, control, and watch documentation. Add
subprocess tests using temporary state and configuration directories; they must
not require audio hardware.

Acceptance: all target-selection examples reach the stated PID, existing
daemon-only examples retain their output, and no test starts another daemon
service.

## Additional work beyond the prompt

None.
