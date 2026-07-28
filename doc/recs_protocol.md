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

## Request/reply commands sent from clients to Recs

After the hello succeeds, clients can send request/reply commands:

```json
{"type":"command","id":"c1","command":"calibrate"}
```

The `id` field is an arbitrary client-chosen string. Recs echoes the same `id`
in the reply. Successful replies have `ok: true` and a command-specific
`result` object. Failed replies have `ok: false` and a `message`.

Current command names:

- `calibrate`
- `capabilities`
- `disk_status`
- `list_devices`
- `mark`
- `pause_recording`
- `reload_profiles`
- `resume_recording`
- `set_key_label`
- `set_noise_floor`
- `start_recording`
- `status_snapshot`
- `stop_recording`

The `shutdown` message is separate from request/reply commands and is described
below.

## Capabilities command

Clients can request protocol version and supported command names:

```json
{"type":"command","id":"c1","command":"capabilities"}
```

Successful reply:

```json
{
  "type": "reply",
  "id": "c1",
  "ok": true,
  "result": {
    "version": 1,
    "commands": ["calibrate", "capabilities"]
  }
}
```

The `commands` list is abbreviated above. Clients should use the actual reply
rather than assuming this document is exhaustive for future protocol versions.

## Status snapshot command

Clients can request one IPC snapshot instead of combining the status file and
live row stream:

```json
{"type":"command","id":"c1","command":"status_snapshot"}
```

Successful reply:

```json
{
  "type": "reply",
  "id": "c1",
  "ok": true,
  "result": {
    "disk": {
      "path": "/home/user/recs",
      "total_bytes": 1000000000,
      "used_bytes": 400000000,
      "free_bytes": 600000000
    },
    "devices": [],
    "errors": [],
    "recording": {
      "paused": false,
      "stopped": false
    },
    "rows": []
  }
}
```

## Recording lifecycle commands

Clients can pause or stop active source recorders while keeping the daemon
alive:

```json
{"type":"command","id":"c1","command":"pause_recording"}
{"type":"command","id":"c2","command":"stop_recording"}
```

Both commands stop currently running source recorders. `stop_recording` also
sets `stopped: true` in the recording state. The daemon remains alive and
continues device and IPC monitoring.

Clients can allow recording to start again:

```json
{"type":"command","id":"c3","command":"resume_recording"}
{"type":"command","id":"c4","command":"start_recording"}
```

Both commands clear the paused and stopped state. Matching devices are started
again on the next device poll.

Lifecycle commands write manifest events:

- `recording_paused`
- `recording_resumed`

The event `label` identifies the command reason, such as `pause_recording`,
`stop_recording`, `resume_recording`, or `start_recording`.

Successful reply:

```json
{
  "type": "reply",
  "id": "c1",
  "ok": true,
  "result": {
    "paused": true,
    "stopped": false
  }
}
```

## Device and disk status commands

Clients can request current source/device status:

```json
{"type":"command","id":"c1","command":"list_devices"}
```

Successful reply:

```json
{
  "type": "reply",
  "id": "c1",
  "ok": true,
  "result": {
    "devices": [
      {
        "name": "Mic",
        "channels": 1,
        "sample_rate": 48000,
        "online": true
      }
    ]
  }
}
```

Clients can request current output disk status:

```json
{"type":"command","id":"c2","command":"disk_status"}
```

Successful reply:

```json
{
  "type": "reply",
  "id": "c2",
  "ok": true,
  "result": {
    "path": "/home/user/recs",
    "total_bytes": 1000000000,
    "used_bytes": 400000000,
    "free_bytes": 600000000
  }
}
```

## Marker and key-label commands

Clients can write a generic marker into the session manifest:

```json
{"type":"command","id":"c1","command":"mark","label":"guitar solo"}
```

`label` is required. Recs writes a `mark` manifest event.

Clients can set or replace a key label used for later key events:

```json
{"type":"command","id":"c2","command":"set_key_label","key":"g","label":"guitar solo"}
```

Both `key` and `label` are required.

## Noise-floor commands

Clients can ask Recs to calibrate per-device noise floors from the audio
observed so far:

```json
{"type":"command","id":"c1","command":"calibrate"}
```

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

Clients can also set a specific source noise floor:

```json
{
  "type": "command",
  "id": "c2",
  "command": "set_noise_floor",
  "source": "Mic",
  "noise_floor": 42.5
}
```

`source` and `noise_floor` are required. This also requires `--profiles PATH`.

Clients can reload profiles from disk for future source starts:

```json
{"type":"command","id":"c3","command":"reload_profiles"}
```

Reloading requires `--profiles PATH`. It updates the parent daemon configuration
used for future source starts. It does not restart active audio source
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
