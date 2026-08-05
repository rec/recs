# Local daemon extraction plan

## Goal

Extract a small reusable local-daemon project for Python tools that need to run
as long-lived per-user services on the same machine.

The first consumers are:

- `recs`: records audio, exposes local GUI/control IPC, and already owns
  cross-platform service install/control code.
- `showco`: runs a local web control UI, supervises helper processes, reads and
  controls `recs`, and is installed as a user `systemd` service by provisioning.
- `lyte`: will listen for MIDI and send UDP lighting updates to network strings.

The reusable project should provide the daemon substrate only. App-specific
recording, lighting, streaming, web UI, device models, and command payloads stay
in their own projects.

## Non-goals

- Do not extract `recs` recording commands or status rows as a generic API.
- Do not extract the `showco` HTTP UI.
- Do not extract `lyte` MIDI or UDP lighting behavior.
- Do not require one IPC protocol payload shape for every app command.
- Do not force every project to support every platform on day one.

## Shared daemon shape

The common pieces are:

- per-user service install, uninstall, start, stop, restart, and status
- service metadata file with executable, argv, platform, and control endpoint
- health/status file for low-rate polling by other local tools
- local JSON-line IPC with hello, request/reply command messages, errors, and
  shutdown
- graceful shutdown that ignores duplicate shutdown requests
- optional subprocess supervision with restart policy and health state
- predictable logs and paths under platform-appropriate user directories

## Proposed package boundary

Create a separate project with a narrow API, tentatively named
`local-daemon`.

Core modules:

- `local_daemon.models`: service metadata, service paths, status, command
  replies, shutdown/error messages
- `local_daemon.paths`: platform-specific user config/state/service paths
- `local_daemon.service`: install/uninstall/start/stop/restart/status controller
- `local_daemon.renderers`: launchd, systemd user, and Windows scheduled-task
  definitions
- `local_daemon.ipc`: JSON-line local server/client, hello handshake,
  request/reply, broadcast status, shutdown propagation
- `local_daemon.supervisor`: optional child-process supervisor with restart
  policy

App projects provide:

- service name and display name
- executable and daemon argv
- app-specific status model
- app-specific command handler
- optional status-to-rows or status-to-web adapters
- optional process-supervisor command builder

## Phase 1: Make `recs.daemon` extraction-ready

Keep code inside `recs` during this phase.

1. Separate generic daemon code from recorder-specific code by naming.
2. Keep service install/control independent from `recs.cfg`, recorder, audio, and
   UI modules.
3. Keep IPC transport independent from recorder command names.
4. Move recorder-specific command handling into adapter code owned by
   `Recorder`.
5. Keep `recs` metadata/status file contents stable while the internals move.
6. Add tests that prove `recs daemon install/status` behavior does not depend on
   importing recorder/audio modules.

Expected result: `recs.daemon` still exists, but the generic parts can be copied
or moved with little behavior change.

## Phase 2: Define the extracted API from real consumers

Use `recs`, `showco`, and the planned `lyte` daemon contract to validate the
API before moving code.

For each consumer, write a short adapter sketch:

- service name
- command used by the installed service
- metadata path
- status path
- control endpoint
- supported control commands
- shutdown behavior
- health fields
- logging expectations

Do not extract until all three sketches can use the same generic service,
metadata, path, and IPC primitives without app-specific branches in the shared
package.

## Phase 3: Create the new project

Create the new repository only after Phase 2 produces a stable API.

Initial project contents:

- Python package `local_daemon`
- no app-specific dependencies
- pydantic models only if the consuming projects already depend on pydantic or
  the model validation value is worth the dependency
- tests copied from `recs.daemon` and generalized
- example app showing a minimal status file, IPC command, and shutdown

Initial supported targets:

- Linux user `systemd`, because `showco` and likely `lyte` need it on the Pi.
- macOS launchd if `recs` still needs local Mac daemon workflows.
- Windows scheduled task can follow after Linux/macOS unless current `recs`
  support must remain exact during extraction.

## Phase 4: Adopt in `recs`

Adopt the extracted package in `recs` first because `recs` has the most complete
daemon implementation today.

1. Replace generic `recs.daemon` internals with calls into `local_daemon`.
2. Keep `recs.daemon` public imports as compatibility wrappers during the
   transition if `showco` still imports them.
3. Preserve metadata paths, status paths, protocol version, and wire messages.
4. Run the full `recs` test suite.
5. Update `doc/recs_protocol.md` only for implementation details that actually
   changed.

## Phase 5: Adopt in `showco`

`showco` should use the extracted package in two places:

- install/manage `showco.service` instead of writing the service file directly
  in provisioning
- reuse IPC/client helpers where they match the `recs` control pattern

Do not force the `showco` HTTP UI through the daemon IPC abstraction. The web UI
is app behavior, not daemon substrate.

Keep the `TwitchoSupervisor` and `X18RecorderSupervisor` local until
`local_daemon.supervisor` can replace them without losing their simple current
behavior.

## Phase 6: Adopt in `lyte`

Use `lyte` as the first clean consumer that was designed after extraction.

Initial `lyte` daemon contract should include:

- MIDI input status
- UDP target status
- last MIDI event time
- last UDP send time
- last error
- commands for shutdown, reload config, pause output, resume output, and
  optionally set scene/preset

This phase validates that the extracted API is not accidentally recorder- or
show-control-specific.

## Risk controls

- Extract behavior only after tests exist in the source project.
- Preserve existing wire formats until consumers are migrated.
- Keep app-specific payload validation in the app.
- Avoid adding dependencies to the shared project unless all consumers already
  tolerate them.
- Avoid cross-platform promises before each platform has direct tests or manual
  acceptance steps.
- Keep service names, paths, and protocol versions explicit inputs, not globals.

## First concrete step

In `recs`, add a boundary test that importing service install/control code does
not import recorder/audio/device modules. That test will expose the first lazy
import cuts and protect the future extraction.

## Additional work beyond the prompt

None.
