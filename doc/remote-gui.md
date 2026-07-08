# Remote GUI plan

## Goal

If `recs` is already running as a daemon and the user starts a new GUI instance,
the new process should connect to the daemon instead of starting a second
recorder.

The daemon process should produce GUI row updates as usual, but send them to any
connected GUI listeners. GUI listeners should send key events back to the daemon.

## User-facing behavior

When no daemon is running:

```sh
recs --gui
```

continues to start a normal local recording session with a GUI.

When the daemon is running:

```sh
recs --gui
```

opens a GUI attached to the daemon and does not start another recorder.

The daemon continues recording if:

1. no GUI is open;
2. one GUI is open;
3. multiple GUIs are open;
4. a GUI crashes or disconnects.

## IPC strategy

Use a local, per-user IPC endpoint.

Do not use TCP for v1. This is not a network feature.

Recommended endpoints:

- macOS and Linux: Unix domain socket in the per-user `recs` state directory.
- Windows: named pipe, such as `\\.\pipe\recs`.

Store the selected endpoint in daemon metadata so clients can find it.

Use newline-delimited JSON messages. This keeps the protocol inspectable and easy
to test.

## Protocol

Add pydantic message models for the daemon GUI protocol.

Initial message types:

```json
{"type": "hello", "role": "gui", "version": 1}
{"type": "rows", "rows": []}
{"type": "key_pressed", "key": "g"}
{"type": "key_released", "key": "g"}
{"type": "shutdown"}
{"type": "error", "message": "..."}
```

Rules:

1. Clients send `hello` after connecting.
2. The daemon sends `rows` whenever the live display would normally refresh.
3. GUI clients send `key_pressed` and `key_released`.
4. Unknown or malformed messages are ignored after logging.
5. A broken client connection is removed.
6. A broken client connection must never stop recording.

## Recorder changes

Split GUI output from recorder row generation.

Current shape:

- `Recorder.rows()` produces row dictionaries.
- `GuiProcess.update()` launches a child GUI process and writes rows to stdin.
- The child process renders rows through the PySide GUI.

Target shape:

- `LocalGuiProcess` keeps the current child-process GUI behavior.
- `DaemonGuiServer` accepts GUI listeners and broadcasts row updates.
- `RemoteGuiClient` connects to the daemon and feeds rows into the existing PySide GUI.

The daemon should not launch a local GUI process. It should publish rows to the
IPC server.

## Daemon behavior

When recording as a daemon:

1. Force terminal display off.
2. Do not create a local `GuiProcess`.
3. Start the GUI IPC server.
4. Broadcast `Recorder.rows()` to every connected listener on each UI refresh.
5. Receive key events from listeners.
6. Feed those key events into the existing recorder key-event path.
7. Continue recording when listeners disconnect.

The daemon should support zero or more listeners.

If two GUI clients send key events, both clients' events count. Do not add
focus, ownership, or locking rules in v1.

## `recs --gui` startup behavior

Update startup behavior:

1. If `--gui` is absent, keep current behavior.
2. If `--gui` is present, check daemon metadata.
3. If daemon metadata exists, check whether the GUI IPC endpoint is reachable.
4. If reachable, run only the remote GUI client.
5. If not reachable, fall back to the current local GUI recording session.

This preserves current behavior when no daemon is running.

## Remote GUI client

Reuse the existing PySide GUI.

Add a row provider similar to `StdinRows`, but backed by the daemon IPC client:

1. A background thread reads `rows` messages.
2. The provider stores the latest rows.
3. The PySide GUI refreshes from the latest rows.
4. Key press/release events are sent back to the daemon.
5. If the daemon disconnects, the GUI closes.

For v1, do not attempt reconnect. The user can run `recs --gui` again.

## Failure handling

Daemon-side failures:

- Client disconnects: remove the client.
- Client sends bad JSON: log and keep the connection unless repeated failures make removal simpler.
- Client write fails: remove the client.
- IPC server cannot start: daemon continues recording and logs the problem.

Client-side failures:

- Daemon endpoint missing: fall back to local GUI recording.
- Daemon disconnects after GUI opens: close GUI.
- Bad daemon message: ignore and keep listening.

## Tests

Unit tests:

1. Protocol models parse valid messages.
2. Protocol models reject malformed messages.
3. Daemon publisher broadcasts rows to multiple fake listeners.
4. Broken listeners are removed.
5. Broken listener writes do not raise out of the publisher.
6. Remote row provider exposes the latest rows.
7. Remote row provider sends key events to the client connection.
8. `recs --gui` selects remote GUI when daemon metadata and endpoint are reachable.
9. `recs --gui` falls back to local recording when the endpoint is absent.
10. Daemon mode does not launch a local GUI process.

Integration-style test:

- Use a local in-process socket or pipe abstraction to verify one daemon publisher
  and one GUI client can exchange `rows` and key-event messages.

Do not install or start native OS services in tests.

## Acceptance criteria

1. Starting `recs --gui` with no daemon running behaves as it does now.
2. Starting `recs --gui` with the daemon running opens a GUI attached to the daemon.
3. Attached GUI startup does not start a second recorder.
4. The daemon keeps recording if the GUI exits.
5. Multiple GUI windows can attach at once.
6. Key events from a remote GUI are recorded in the daemon session manifest.
7. GUI IPC failure cannot crash the recorder.
8. Tests do not install or start native services.

## Non-goals

1. Do not add remote network access.
2. Do not add authentication for v1, because the endpoint is local and per-user.
3. Do not add GUI reconnect logic.
4. Do not add focus ownership between multiple GUIs.
5. Do not make the daemon itself show a GUI.
