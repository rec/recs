# Recs protocol

The public Recs API is a local two-way RPC service provided by `reccy.rpc`.
It is available only while the Recs daemon is running. The daemon GUI socket is
private implementation detail and is not a public API.

The RPC transport version is `reccy.rpc.VERSION`. The Recs payload version is
`recs.daemon.gui_protocol.VERSION`; they are independent.

## Endpoints

On macOS and Linux, the daemon owns these Unix sockets:

- `~/.local/state/recs/control.sock`
- `~/.local/state/recs/events.sock`

On Windows, the endpoints are named pipes:

- `\\.\pipe\recs-control`
- `\\.\pipe\recs-events`

Use `recs.daemon.paths.external_control_endpoint()` and
`external_event_endpoint()` rather than duplicating these paths in a client.

## Control requests

Each control connection begins with Reccy's hello handshake, sends one request,
receives one response, and closes. A request has an RPC `id`, a Recs command
name, and the remaining fields in `params`:

```json
{
  "type": "request",
  "id": "request-1",
  "command": "set_cfg",
  "params": {
    "address": "recording.longest_file_time",
    "value": 3600
  }
}
```

This is equivalent to the Recs request payload:

```json
{"type":"set_cfg","address":"recording.longest_file_time","value":3600}
```

The Recs daemon validates and executes it in the recorder loop. The RPC handler
does not read devices, process audio, or write recordings.

A successful result includes the complete typed Recs response payload. The
payload `type` is retained so callers can route by response type:

```json
{
  "type": "response",
  "id": "request-1",
  "ok": true,
  "result": {
    "type": "cfg_set",
    "address": "recording.longest_file_time",
    "value": 3600
  }
}
```

Invalid commands and command failures return `ok: false` with an explanatory
`message`. RPC handshake and malformed-message failures use Reccy IPC errors.

## Commands

`command` is the corresponding Recs request `type`; `params` contains the
other request fields.

| Command | Typed result |
| --- | --- |
| `calibrate` | `calibrated` with per-track `measurements` and applied `noise_floors` |
| `capabilities` | `capabilities_result` with `commands` and Recs payload version |
| `disk_status` | `disk_status_result` with filesystem usage |
| `get_cfg` | `cfg_value` with `address` and `value` |
| `set_cfg` | `cfg_set` with normalized `address` and `value` |
| `get_track_names` | `track_names` |
| `set_track_names` | `track_names` |
| `set_tracks` | `tracks_set` |
| `list_devices` | `devices` |
| `mutable_attributes` | `mutable_attributes_result` |
| `mark` | `marked` |
| `pause_recording` | `recording_state` |
| `resume_recording` | `recording_state` |
| `start_recording` | `recording_state` |
| `stop_recording` | `recording_state` |
| `reload_profiles` | `profiles_reloaded` |
| `set_key_label` | `key_label_set` |
| `set_noise_floor` | `noise_floor_set` |
| `status_snapshot` | `status_snapshot_result` |
| `shutdown` | final `recording_state` |

`calibrate` accepts an optional `channels` object mapping device names to mono
channels or a member of each stereo pair. `set_noise_floor` accepts `null` to
clear a channel or stereo-pair override. `set_tracks` changes the files for the
affected tracks on the next input frame. `set_cfg` is limited to the mutable
attributes returned by `mutable_attributes`.

## Events

An event client completes the same hello handshake on the events endpoint, then
sends `{"type":"subscribe"}` and keeps the connection open.

The daemon publishes the normal live-display information as a `rows` event:

```json
{
  "type": "event",
  "name": "rows",
  "data": {
    "rows": [{"device":"Mic"}],
    "errors": [{"timestamp":"...Z","message":"..."}]
  }
}
```

`rows` events use the same update cadence and data as the daemon GUI. Use
`status_snapshot` when an immediate full snapshot is required.

## Shutdown

The `shutdown` command starts the existing one-shot daemon shutdown. The first
request receives the final `recording_state`. Later shutdown requests do not
start another shutdown. Before closing the event endpoint, the daemon publishes
one `{"type":"event","name":"shutdown","data":{}}` event, then closes
all event subscriptions.
