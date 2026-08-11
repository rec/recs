# Recs protocol

The Recs daemon accepts newline-delimited JSON on its local GUI endpoint. This
is protocol version 2. It is not compatible with version 1.

The client begins with:

```json
{"type":"hello","role":"gui","version":2}
```

The daemon answers before processing any other message:

```json
{"type":"hello","role":"daemon","version":2}
```

Clients send one request and read its direct response before sending another
request on the same connection. Requests are queued for the recorder loop; the
response is written to that same connection once the recorder loop has handled
the request. There are no message IDs and no generic reply message.

Errors use `{"type":"error","message":"..."}`.

## Requests and responses

| Request | Direct response |
| --- | --- |
| `{"type":"calibrate"}` | `calibrated` with per-track `measurements` and applied `noise_floors` |
| `{"type":"calibrate","channels":{"Mic":[1,3]}}` | calibrates selected physical channels; a selected member of a stereo pair calibrates that pair |
| `{"type":"capabilities"}` | `capabilities_result` with `commands` and `version` |
| `{"type":"disk_status"}` | `disk_status_result` with `free_bytes`, `path`, `total_bytes`, and `used_bytes` |
| `{"type":"get_cfg","address":"recording.longest_file_time"}` | `cfg_value` with `address` and `value` |
| `{"type":"set_cfg","address":"recording.longest_file_time","value":3600}` | `cfg_set` with the normalized `address` and `value` |
| `{"type":"get_track_names"}` | `track_names` with `track_names` |
| `{"type":"set_track_names","track_names":{"Mic":{"Lead Vocal":1}}}` | `track_names` with `track_names` |
| `{"type":"list_devices"}` | `devices` with `devices` |
| `{"type":"mutable_attributes"}` | `mutable_attributes_result` with `mutable_attributes` |
| `{"type":"mark","label":"guitar solo"}` | `marked` with `label` |
| `{"type":"pause_recording"}` | `recording_state` with `paused` and `stopped` |
| `{"type":"resume_recording"}` | `recording_state` with `paused` and `stopped` |
| `{"type":"start_recording"}` | `recording_state` with `paused` and `stopped` |
| `{"type":"stop_recording"}` | `recording_state` with `paused` and `stopped` |
| `{"type":"reload_profiles"}` | `profiles_reloaded` with `profiles_path` |
| `{"type":"set_key_label","key":"g","label":"guitar solo"}` | `key_label_set` with `key` and `label` |
| `{"type":"set_noise_floor","source":"Mic","channel":1,"noise_floor":42.5}` | `noise_floor_set` with `source`, `channel`, and `noise_floor`; `null` clears the override |
| `{"type":"status_snapshot"}` | `status_snapshot_result` with `disk`, `devices`, `errors`, `recording`, and `rows` |

`set_cfg` validates the requested value with `Cfg`, records `cfg_set` in the
session manifest, and queues the resulting effective configuration for each
source recorder. A source applies queued configuration immediately before its
next audio buffer is processed. `get_cfg` returns the daemon configuration and
records `cfg_get` in the manifest.

`recording.channel_noise_floors` maps device names to selected track names such
as `"1"` and `"1-2"`. Missing entries and `null` values use the global
`recording.noise_floor`. Calibration measures exactly 500 ms of incoming audio
without changing recording state, then applies its channel-specific results
through `set_cfg` behavior.

For example:

```json
{"type":"set_cfg","address":"recording.longest_file_time","value":3600}
{"type":"cfg_set","address":"recording.longest_file_time","value":3600}
```

## Notifications

The daemon may send this notification at any time:

```json
{"type":"rows","rows":[{"device":"Mic"}],"errors":[]}
```

`rows` contains the normal live-display rows. `errors` contains current daemon
errors for display by clients.

Key notifications from GUI clients are `key_pressed` and `key_released`, each
with a `key` string.

## Shutdown

The client can request daemon shutdown with:

```json
{"type":"shutdown"}
```

The daemon broadcasts the same message to all listeners and closes their
connections. A shutdown request received after shutdown has begun is ignored.
