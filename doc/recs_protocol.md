# Recs protocol

Recs exposes a local RPC API while its daemon is running. Clients can use it
to inspect recording state, change mutable recording settings, configure
tracks, add manifest marks, pause or resume recording, and shut down the
daemon.

The public API uses `reccy.rpc`. The separate daemon GUI socket remains a
private implementation detail. Live waveforms are available through the public
control and event endpoints described below.

## Quick start

Use `reccy.rpc.Client` for a control request. It handles the connection,
version handshake, JSON encoding, response, and connection close:

```python
from reccy import rpc

from recs.daemon import paths

client = rpc.Client(
    paths.external_control_endpoint(),
    role='my-client',
    timeout=6,
)
status = client.call('status_snapshot')
```

Every control connection carries exactly one request and one response. Create
a new connection, or call `Client.call()` again, for the next request.

Successful commands return either a JSON object or the string `"ok"`.
`rpc.Client.call()` returns the decoded value. It raises `ConnectionError` when
Recs returns an error.

## Endpoints

On macOS and Linux, Recs owns these Unix sockets:

- `~/.local/state/recs/control.sock` for requests
- `~/.local/state/recs/events.sock` for subscriptions

On Windows, it owns these named pipes:

- `\\.\pipe\recs-control`
- `\\.\pipe\recs-events`

Clients should call `recs.daemon.paths.external_control_endpoint()` and
`external_event_endpoint()` instead of duplicating these paths.

The API is local only. Recs does not open a TCP port or provide authentication
or network transport.

## Versions

There are two independent versions:

- `reccy.rpc.VERSION` is the transport version. It is currently `1` and is
  exchanged during every connection handshake.
- `recs.daemon.gui_protocol.VERSION` is the Recs payload version. It is
  currently `5` and is returned by `capabilities`.

A client normally does not need to import either constant because
`reccy.rpc.Client` handles the transport handshake and `capabilities` reports
the payload version.

## Commands

The `capabilities` response is the authoritative list of commands supported by
the running daemon. Commands in the following table that do not have a data
response return the JSON string `"ok"`.

| Command | Parameters | Success response |
| --- | --- | --- |
| `capabilities` | none | `capabilities_result` |
| `status_snapshot` | none | `status_snapshot_result` |
| `disk_status` | none | `disk_status_result` |
| `list_devices` | none | `devices` |
| `mutable_attributes` | none | `mutable_attributes_result` |
| `get_cfg` | `address: str` | `cfg_value` |
| `set_cfg` | `address: str`, `value` | `"ok"` |
| `get_track_names` | none | `track_names` |
| `set_track_names` | `track_names: object` | `"ok"` |
| `set_tracks` | `source: str`, `tracks: list` | `"ok"` |
| `set_noise_floor` | `source: str`, `channel: int`, `noise_floor: float | null` | `"ok"` |
| `set_key_label` | `key: str`, `label: str` | `"ok"` |
| `calibrate` | optional `channels: object` | `calibrated` |
| `mark` | `label: str` | `"ok"` |
| `card_replace` | none | `card_replace_started` |
| `pause_recording` | none | `"ok"` |
| `resume_recording` | none | `"ok"` |
| `reload_profiles` | none | `"ok"` |
| `subscribe_waveforms` | none | `waveform_subscription` |
| `unsubscribe_waveforms` | none | `waveform_subscription` |
| `shutdown` | none | `"ok"` |

### Capabilities

Call this first when a client needs to adapt to different Recs versions:

```json
{
  "type": "capabilities_result",
  "commands": ["calibrate", "capabilities", "disk_status"],
  "version": 6
}
```

The real `commands` list contains every command supported by that daemon; the
example is abbreviated.

### Status

`status_snapshot` returns the complete current state needed by a monitoring
client:

```json
{
  "type": "status_snapshot_result",
  "devices": [],
  "disk": {
    "free_bytes": 700000000000,
    "path": "/mnt/openloop/recs/2026-08-28 12-00-00/audio/audio-manifest.jsonl",
    "total_bytes": 1000000000000,
    "used_bytes": 300000000000,
    "estimated_seconds_remaining": 86400.0,
    "alert_threshold": null,
    "alert_active": false,
    "automatic_switch_armed": false,
    "paused_for_disk_space": false,
    "resume_disk": null
  },
  "errors": [],
  "manifest_path": "/mnt/openloop/recs/2026-08-28 12-00-00/audio/audio-manifest.jsonl",
  "midi": [],
  "osc": [],
  "recording": {"paused": false},
  "rows": [],
  "session_directory": "/mnt/openloop/recs/2026-08-28 12-00-00"
}
```

The fields have these meanings:

| Field | Meaning |
| --- | --- |
| `devices` | Configured audio sources, including channel count, sample rate, and whether each source is online |
| `disk` | The same object returned by `disk_status`, without its `type` field |
| `errors` | Recorded errors, each with `timestamp`, `message`, and optional boolean `value` |
| `manifest_path` | Absolute path of the current session manifest |
| `midi` | Current MIDI input states |
| `osc` | Current OSC recorder states |
| `recording.paused` | Whether recording is globally paused |
| `rows` | The current live-display rows described under Events |
| `session_directory` | Absolute path of the current session directory |

`disk_status` returns filesystem usage for the current manifest path, or its
nearest existing ancestor when the manifest does not exist yet:

```json
{
  "type": "disk_status_result",
  "free_bytes": 700000000000,
  "path": "/mnt/openloop/recs/2026-08-28 12-00-00/audio/audio-manifest.jsonl",
  "total_bytes": 1000000000000,
  "used_bytes": 300000000000,
  "estimated_seconds_remaining": 86400.0,
  "alert_threshold": null,
  "alert_active": false,
  "automatic_switch_armed": false,
  "paused_for_disk_space": false,
  "resume_disk": null
}
```

`estimated_seconds_remaining` is `null` until Recs has measured a nonzero
write rate. `resume_disk` is the path of a removable disk with enough free
space to resume, or `null`.

`list_devices` returns configured sources. Each item has `name`, `channels`,
`sample_rate`, and `online` fields.

### Configuration

Configuration addresses use dotted names such as
`recording.longest_file_time`:

```python
value = client.call('get_cfg', address='recording.longest_file_time')
client.call(
    'set_cfg',
    address='recording.longest_file_time',
    value=3600,
)
```

`get_cfg` returns:

```json
{
  "type": "cfg_value",
  "address": "recording.longest_file_time",
  "value": 3600.0
}
```

`get_cfg` can read any valid configuration address. `set_cfg` can change only
addresses returned by `mutable_attributes`. Recs validates and coerces the new
value, applies it to active source processes, records the change in the
manifest, and saves it when `save_settings` is enabled.

### Tracks and names

A track is one mono channel or two adjacent channels. Stereo pairs may start
on either an odd or even channel. Tracks cannot share channels, and a request
cannot replace only one channel of an existing stereo track.

`set_tracks` replaces the tracks touched by the request and leaves other tracks
on that source unchanged. It applies the change on the next input frame:

```python
client.call(
    'set_tracks',
    source='X18: USB Audio (hw:0,0)',
    tracks=[
        {'channels': [1], 'name': 'Vocal'},
        {'channels': [2, 3], 'name': 'Keys'},
    ],
)
```

At least one track is required. Channel numbers are one-based, ascending, and
must exist on the source.

Track names use this shape:

```json
{
  "X18: USB Audio (hw:0,0)": {
    "Vocal": 1,
    "Keys": 2
  }
}
```

The outer key is the source key. Each inner key is a display name and its value
is the track's first channel. `get_track_names` returns this object inside a
`track_names` response. `set_track_names` replaces the complete mapping.

`set_noise_floor` identifies a track by any channel in that track. A numeric
value sets its override; `null` clears the override.

### Calibration

With no `channels` parameter, `calibrate` measures every track on every online
audio source. To select tracks, map source names to one or more channel
numbers:

```python
result = client.call(
    'calibrate',
    channels={'X18: USB Audio (hw:0,0)': [1, 2]},
)
```

For a stereo track, either channel selects the whole track. Repeated channels
from the same track are deduplicated. The response contains flattened measured
levels and the per-source noise floors that Recs applied:

```json
{
  "type": "calibrated",
  "measurements": {
    "X18: USB Audio (hw:0,0) - 1": -48.2,
    "X18: USB Audio (hw:0,0) - 2-3": -51.0
  },
  "noise_floors": {
    "X18: USB Audio (hw:0,0)": {
      "1": -39.2,
      "2-3": -42.0
    }
  }
}
```

Calibration also updates `recording.channel_noise_floors`.

### Recording control

### Card replacement

`card_replace` prepares Recs for replacing the removable card that contains
the current output directory. It is intended for a machine with a single card
reader: send the command before removing the old card, then insert the new
one in the same reader.

The command closes and syncs every active audio, MIDI, and OSC file and
manifest on the old card, records the old card's filesystem UUID in those
manifests, and leaves the card mounted. Capture continues, but Recs holds
received audio blocks, MIDI messages, and OSC packets in memory instead of
writing to the old card. The success response identifies the old card and the
replacement deadline:

```json
{
  "type": "card_replace_started",
  "old_mount": "/mnt/openloop",
  "old_uuid": "6A1B-2C3D",
  "deadline": "2026-08-28T12:05:00.000Z"
}
```

Recs polls mounted recording disks every
`recording.card_replace_poll_seconds` (default `1`) for a disk whose UUID
differs from `old_uuid`. On finding one, it creates a new session directory on
that disk, writes the retained audio blocks, MIDI messages, and OSC packets to
their new session files, and then writes newly received data normally. The
configured output directory is not changed or saved: Recs applies the relative
path from the old card's mount point to the new card's mount point for this
session only.

While Recs is waiting for a replacement card, `rows` events and
`status_snapshot` include an error record with `message` set to `"awaiting
card"` and `value` set to `true`. When Recs finds a destination card, that
same record has `value` set to `false`.

If no different UUID appears within
`recording.card_replace_timeout_seconds` (default `300`), Recs resumes on the
old card only when that card is still mounted. It creates a new session
directory there before draining all retained media.

The retained audio backlog is bounded by
`recording.audio_buffer_seconds` and the memory reserve. Once a source buffer
fills, Recs drops subsequent frames and records the existing `buffer_overflow`
information when recording resumes. Set `audio_buffer_seconds` high enough for
the expected physical card-change time and the available memory.
`card_replace` fails without changing recording when the current output
directory is not on a mounted recording disk with a discoverable filesystem
UUID.

`pause_recording` closes active audio recordings and prevents further audio
recording. `resume_recording` clears that global pause, allowing audio sources
to begin writing new files. MIDI and OSC recording continue while audio is
paused. Both transitions are recorded in the manifest.

Use `status_snapshot` to read the resulting `recording.paused` state.

`mark` appends a labeled event to the current manifest. `set_key_label`
updates the label associated with a recorded key. `reload_profiles` reloads the
configured profiles file and fails if Recs was not started with a profiles
path.

## Live waveforms

Waveforms use both public endpoints. Start an `EventClient` first, then call
`subscribe_waveforms` on the control endpoint:

```python
from reccy import rpc

from recs.base.waveform import WaveformBatchData, WaveformLayoutData
from recs.daemon import paths


def receive(event: rpc.Event) -> None:
    if event.name == 'waveform_layout':
        layout = WaveformLayoutData.model_validate(event.data)
        display.set_layout(layout)
    elif event.name == 'waveform':
        batch = WaveformBatchData.model_validate(event.data)
        display.add_batch(batch)


events = rpc.EventClient(
    paths.external_event_endpoint(),
    receive,
    role='showco',
)
events.start()

control = rpc.Client(
    paths.external_control_endpoint(),
    role='showco',
    timeout=6,
)
subscription = control.call('subscribe_waveforms')
```

The subscription response reports the active state and configured timing:

```json
{
  "type": "waveform_subscription",
  "active": true,
  "bucket_milliseconds": 20,
  "batch_milliseconds": 100
}
```

Subscription is transient and has no history. Enabling it starts envelope
reduction on every active audio source. A source sends a `waveform_layout`
event before batches for that layout:

```json
{
  "type": "event",
  "name": "waveform_layout",
  "data": {
    "source": "X18: USB Audio (hw:0,0)",
    "generation": 3,
    "sample_rate": 48000,
    "bucket_frames": 960,
    "tracks": [
      {"channels": [1], "name": "Vocal"},
      {"channels": [2, 3], "name": "Keys"}
    ]
  }
}
```

Each `waveform` event contains one bounded min/max envelope batch:

```json
{
  "type": "event",
  "name": "waveform",
  "data": {
    "source": "X18: USB Audio (hw:0,0)",
    "generation": 3,
    "sequence": 42,
    "sample_rate": 48000,
    "bucket_frames": 960,
    "start_frame": 196800,
    "start_timestamp": 1788000004.1,
    "present": [true, true, true, true, true],
    "tracks": [
      {
        "channels": [1],
        "minimum": [[-0.12, -0.18, -0.09, -0.04, -0.14]],
        "maximum": [[0.10, 0.16, 0.08, 0.05, 0.13]]
      }
    ],
    "dropped_batches": 0
  }
}
```

`generation` changes when a source's layout or waveform stream restarts.
Clients must discard retained data from older generations. `present` marks
which bucket positions contain valid captured audio. A false value is a gap,
not digital silence. `sequence` gaps and `dropped_batches` report transport
drops.

Public delivery retains at most five pending batches per source and discards
the oldest first, so a slow event connection cannot delay audio recording.
Call `unsubscribe_waveforms` when waveform events are no longer needed, then
close the event client. Unsubscribing clears pending waveform events and stops
envelope reduction. Closing only the event connection does not issue that
control command.

## Events

An event subscription is a separate long-lived connection. Use
`reccy.rpc.EventClient`:

```python
from reccy import rpc

from recs.daemon import paths


def receive(event: rpc.Event) -> None:
    print(event.name, event.data)


events = rpc.EventClient(
    paths.external_event_endpoint(),
    receive,
    role='my-monitor',
)
events.start()
```

The callback runs on the event client's background reader thread. Keep the
`EventClient` alive for as long as events are needed and call `events.close()`
to disconnect.

Recs publishes these events:

| Event | Data |
| --- | --- |
| `rows` | `rows` live-display records and current `errors` |
| `waveform_layout` | Current track layout and waveform generation for one source |
| `waveform` | One min/max envelope batch for one source |
| `shutdown` | empty; Recs has begun shutting down |
| `stopped` | empty; the Reccy service lifecycle has stopped |

A `rows` event looks like this:

```json
{
  "type": "event",
  "name": "rows",
  "data": {
    "rows": [
      {"time": 120.0, "recorded": 200.0, "file_size": 19200000, "file_count": 2},
      {"device": "Mixer", "on": "active"},
      {
        "channel": "Vocal",
        "channels": [1],
        "on": "active",
        "recorded": 120.0,
        "file_size": 11520000,
        "file_count": 1,
        "signal": -32.4,
        "volume": -32.4
      }
    ],
    "errors": []
  }
}
```

The first row contains session totals. A device row identifies a source and
reports `active` or `offline`. Its following track rows report `active` or
`inactive`, channel numbers, recorded duration, file totals, and current signal
level. These are complete display snapshots, not incremental changes.

`rows` events use the live-display refresh cadence. Use `status_snapshot` when
an immediate snapshot is required. Waveform events use the independently
configured bucket and batch cadence.

## Shutdown

`shutdown` returns `"ok"` after scheduling the daemon's existing one-shot
shutdown. Repeating it does not start a second shutdown.

Before closing event subscriptions, Recs publishes one `shutdown` event and
then the Reccy lifecycle publishes one `stopped` event.

## Errors and limits

Errors use this wire shape:

```json
{"type":"error","message":"explanation"}
```

`reccy.rpc.Client` converts this to `ConnectionError(message)`. Raw clients
must decode it themselves.

Only one control request may be awaiting the Recs recorder at a time. A second
request receives `recs already has an active control client`.

Recs waits at most five seconds for the recorder loop to answer an external
request. The Reccy client has its own timeout, which defaults to one second;
choose a timeout appropriate for the command. A client timeout closes only the
client connection and does not cancel a command that the recorder has already
received.

The current calibration implementation can wait up to 15 seconds internally,
which is longer than the external five-second response limit. A slow
calibration can therefore return a timeout even though processing continues in
the recorder. This is a current protocol limitation.

The Reccy transport allows at most 64 KiB in one request and requires the
version handshake to complete within one second.

## Raw wire format

The transport is newline-delimited JSON. A raw control client performs this
exchange:

1. Connect to the control endpoint.
2. Send `{"type":"hello","role":"my-client","version":1}`.
3. Receive `{"type":"hello","role":"recs","version":1}`.
4. Send one request.
5. Receive one result or error.
6. Observe the server closing the connection.

A request contains a command and all command-specific fields in `params`:

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

An event client performs the same handshake on the event endpoint, then sends
`{"type":"subscribe"}` and keeps the connection open. Every subsequent line
is a Reccy `event` object until the client or server closes the connection.
