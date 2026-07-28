# Recs protocol

This document describes the files and messages that clients use to communicate
with a running `recs` daemon.

Clients read the Recs daemon status file for low-rate status and can connect to
the Recs GUI IPC endpoint for live row updates and control commands.

The current control commands exposed to clients are live noise-floor
calibration and daemon shutdown. Recs does not expose GUI IPC commands for
starting recording or changing arbitrary recording configuration.

## Status file

Clients read the Recs daemon status file.

Platform paths:

- macOS and Linux: `~/.local/state/recs/status.json`
- Windows: `%LOCALAPPDATA%\recs\status.json`

The file contains one JSON object. Current fields are:

```json
{
  "client_count": 0,
  "errors": [],
  "gui_ipc_error": null,
  "rows": [],
  "recording": false,
  "updated_at": 0.0
}
```

Field meanings:

- `client_count`: number of connected GUI IPC clients.
- `errors`: current recorder errors and warnings shown by the Recs UI.
- `gui_ipc_error`: latest GUI IPC startup error, or `null`.
- `rows`: current display rows, described below.
- `recording`: whether the daemon reports that recording is active.
- `updated_at`: Unix timestamp of the last daemon status update.

Clients should treat the Recs status as stale when `updated_at` is more than
three seconds old.

## Row objects

`rows` is the same table-oriented data that Recs sends to its GUI. Every row is a
JSON object. Fields are sparse, so a row only includes values that apply to that
row.

The total row may contain:

```json
{
  "time": 12.34,
  "recorded": 11.2,
  "file_size": 123456,
  "file_count": 2
}
```

A device row may contain:

```json
{
  "device": "MacBook Pro Microphone",
  "on": "active"
}
```

A channel row may contain:

```json
{
  "channel": "1",
  "on": "active",
  "recorded": 11.2,
  "file_size": 123456,
  "file_count": 1,
  "signal": 0.42,
  "volume": 0.42
}
```

Current `on` values are produced by Recs and are treated as display data.
Clients do not send them back to Recs.

Clients can map channel `signal` to four display states:

- missing, `null`, or less than `0.001`: `silent`
- at least `0.001` and less than `0.3333333333`: `present`
- at least `0.3333333333` and less than `0.9`: `healthy`
- at least `0.9`: `clipping`

## GUI IPC endpoint

Recs stores the GUI endpoint in daemon metadata.

Metadata paths:

- macOS and Linux: `~/.config/recs/daemon.json`
- Windows: `%APPDATA%\recs\daemon.json`

The current metadata object is:

```json
{
  "version": 1,
  "argv": [],
  "executable": "/path/to/recs",
  "platform": "linux",
  "gui_endpoint": "/home/user/.local/state/recs/gui.sock"
}
```

Endpoint values:

- macOS and Linux: Unix-domain socket path.
- Windows: named pipe string `\\.\pipe\recs`.

Each GUI IPC message is one JSON object. On Unix sockets each message is sent as
one UTF-8 JSON line. On Windows named pipes each message is sent as one pipe
message containing the JSON text.

## Handshake

The first live IPC message sent by a client must be the GUI hello:

```json
{"type":"hello","role":"gui","version":1}
```

Recs requires this hello before any other live IPC message.

After a valid hello, Recs replies:

```json
{"type":"hello","role":"daemon","version":1}
```

If the client sends any other message before hello, Recs replies and closes the
connection:

```json
{"type":"error","message":"GUI hello required before other messages"}
```

If the client sends an unsupported protocol version, Recs replies and closes the
connection:

```json
{"type":"error","message":"GUI protocol version 2 is not supported; daemon requires 1"}
```

## Status updates sent from Recs to clients

Recs sends live row updates:

```json
{
  "type": "rows",
  "rows": [
    {
      "device": "MacBook Pro Microphone",
      "on": "active"
    }
  ],
  "errors": []
}
```

The `rows` payload has the same shape as the status-file `rows` field.
The `errors` payload contains the same current recorder errors and warnings as
the status-file `errors` field.

## Calibration command sent from clients to Recs

After the hello succeeds, clients can ask Recs to calibrate per-device noise
floors from the audio observed so far:

```json
{"type":"command","id":"c1","command":"calibrate"}
```

The `id` field is an arbitrary client-chosen string. Recs echoes the same `id`
in the reply.

Calibration requires that the daemon was started with `--profiles PATH`.
Without a profiles file, Recs cannot persist the calibration and returns an
error.

Successful reply:

```json
{
  "type": "reply",
  "id": "c1",
  "ok": true,
  "result": {
    "measurements": {
      "MacBook Pro Microphone - 1": 6.020599913279624,
      "(all)": 6.020599913279624
    },
    "profiles": {
      "MacBook Pro Microphone": {
        "noise_floor": 12.0
      }
    },
    "profiles_path": "/home/user/recs-profiles.json"
  }
}
```

Failure reply when no profiles file is configured:

```json
{
  "type": "reply",
  "id": "c1",
  "ok": false,
  "message": "Cannot calibrate noise floor without --profiles"
}
```

Recs writes the profile file atomically. Calibration updates the parent daemon
configuration for future source starts. It does not restart active audio source
processes.

## Key event messages

Recs also accepts key event messages after the hello:

```json
{"type":"key_pressed","key":"g"}
{"type":"key_released","key":"g"}
```

Clients do not need to send key events for calibration, but they remain part of
the GUI IPC protocol.

## Shutdown message

After the hello succeeds, clients can ask Recs to stop the running daemon:

```json
{"type":"shutdown"}
```

The first shutdown message starts daemon shutdown. Recs ignores any later
shutdown messages after shutdown has started.

When shutdown starts, Recs propagates the same shutdown message to connected GUI
clients before closing their connections:

```json
{"type":"shutdown"}
```

Recs also sends shutdown to connected GUI clients when the daemon-side GUI IPC
server is stopping for another reason:

```json
{"type":"shutdown"}
```

Clients should close the GUI session after receiving this message.

## Commands not currently available

The current Recs daemon does not expose GUI IPC messages for:

- starting recording
- changing arbitrary recording configuration
