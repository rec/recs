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
receives one direct response, and closes. A request has a Recs command name and
the remaining fields in `params`:

```json
{
  "type": "request",
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

A command with no result returns the JSON string `"ok"`. Commands with data
return the complete typed Recs response payload directly:

```json
{
  "type": "cfg_value",
  "address": "recording.longest_file_time",
  "value": 3600
}
```

Invalid commands and command failures return an `error` payload with an
explanatory `message`.

## Commands

`command` is the corresponding Recs request `type`; `params` contains the
other request fields. Commands not marked with a result return `"ok"`.

| Command | Response |
| --- | --- |
| `calibrate` | `calibrated` with per-track `measurements` and applied `noise_floors` |
| `capabilities` | `capabilities_result` with `commands` and Recs payload version |
| `disk_status` | `disk_status_result` with filesystem usage |
| `get_cfg` | `cfg_value` with `address` and `value` |
| `set_cfg` | `"ok"` |
| `get_track_names` | `track_names` |
| `set_track_names` | `"ok"` |
| `set_tracks` | `"ok"` |
| `list_devices` | `devices` |
| `mutable_attributes` | `mutable_attributes_result` |
| `mark` | `"ok"` |
| `pause_recording` | `"ok"` |
| `resume_recording` | `"ok"` |
| `start_recording` | `"ok"` |
| `stop_recording` | `"ok"` |
| `reload_profiles` | `"ok"` |
| `set_key_label` | `"ok"` |
| `set_noise_floor` | `"ok"` |
| `status_snapshot` | `status_snapshot_result` |
| `shutdown` | `"ok"` |

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
all event subscriptions. Reccy's lifecycle also publishes one `stopped` event
before the connections close.
