# recs protocol

recs exposes a local RPC API while a recorder is running. Clients can use it
to inspect recording state, change mutable recording settings, configure
tracks, add marks to the session record, play a finalized recorded-audio
session, manage musicians and their source-channel assignments, pause or resume
recording, and shut down the daemon.

The public API uses `reccy.protocol.rpc`. The separate daemon GUI socket remains a
private implementation detail. Live waveforms are available through the public
control and event endpoints described below.

## Quick start

Use `reccy.protocol.rpc.Client` for a control request. It handles the connection,
version handshake, JSON encoding, response, and connection close:

```python
from reccy.protocol import rpc

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
recs returns an error.

## Command-line client

`recs control` exposes the common one-request operations without requiring
Python code:

```sh
recs control status
recs control disk
recs control devices
recs control capabilities
recs control mutable
recs control get recording.longest_file_time
recs control set recording.longest_file_time 1h
recs control mark "solo starts"
recs control pause
recs control resume
recs control play
recs control pause-playback
recs control jump -10
recs control continue
recs control stop
recs control calibrate
recs control card-replace
recs control reload-profiles
recs control project-switch x18-show
recs control project-switch  # default workspace
recs control musician-add mike --name Michael --link insta:mike
recs control musician-list
recs control musician-assign mike Ext 1 2
recs control musician-remove mike --source Ext --channel 1
recs control instances
```

By default, `recs control` and `recs watch` select the newest live foreground
instance. When there is none, they use the daemon's established endpoint. Use
`--daemon` to select the daemon, `--instance PID` for a specific instance, or
`--instance -1`, `--instance -2`, and so on for foreground instances ordered
newest first. Negative positions never include the daemon. `recs control
instances` prints the verified live instances and sends no request.

The subcommands map to the protocol as follows:

| CLI subcommand | Protocol command |
| --- | --- |
| `status` | `status_snapshot` |
| `disk` | `disk_status` |
| `devices` | `list_devices` |
| `capabilities` | `capabilities` |
| `mutable` | `mutable_attributes` |
| `get ADDRESS` | `get_cfg` |
| `set ADDRESS VALUE` | `set_cfg` |
| `mark LABEL` | `mark` |
| `pause` | `pause_recording` |
| `resume` | `resume_recording` |
| `play [--session N] [--source NAME] [--channel N[-N]] [--output-channel N[-N]]` | `play_session` |
| `stop` | `stop_playback` |
| `pause-playback` | `pause_playback` |
| `continue` | `continue_playback` |
| `jump SECONDS` | `jump_playback` |
| `jump-session -1\|1` | `jump_session` |
| `calibrate` | `calibrate` for all selected online tracks |
| `card-replace` | `card_replace` |
| `reload-profiles` | `reload_profiles` |
| `project-switch [NAME]` | `switch_project` |
| `musician-add NICKNAME [--name NAME ...] [--public-key KEY ...] [--link VALUE ...]` | `add_musician` |
| `musician-list` | `list_musicians` |
| `musician-edit NICKNAME [--name NAME ...] [--public-key KEY ...] [--link VALUE ...] [--clear-names] [--clear-public-keys] [--clear-links]` | `edit_musician` |
| `musician-delete NICKNAME` | `delete_musician` |
| `musician-assign NICKNAME SOURCE CHANNEL [CHANNEL ...] [--track-name VALUE]` | `assign_musician` |
| `musician-remove NICKNAME [--source SOURCE] [--channel CHANNEL ...]` | `remove_musician` |

Each invocation except `musician-list` prints exactly one JSON value followed by
a newline. `musician-list` prints TOML. Commands without a data response print
`"ok"`. Connection, timeout, daemon, and response validation failures are
printed to standard error and return exit status `1`.

`set` parses `VALUE` as JSON when possible. Numbers, booleans, `null`, arrays,
and objects therefore retain their JSON types. Other values, including unit
strings such as `1h`, are sent as strings. To send a numeric-looking string,
include JSON string quotes in the shell argument:

```sh
recs control set some.address '"3600"'
```

`pause` and `resume` have the audio-only behavior described under Recording
control; MIDI and OSC continue while audio is paused. Waveform subscriptions
are not one-request operations and are not exposed through `recs control`.

## Instances and endpoints

The established endpoints remain the daemon endpoints. Existing clients using
`external_control_endpoint()` or `external_event_endpoint()` therefore continue
to address the one daemon.

An ordinary foreground recorder also starts a control and event server. Its
unique endpoints and identity are published in an atomic descriptor under
`~/.local/state/recs/instances/`; the descriptor disappears on orderly shutdown.
Each descriptor has a PID, opaque start token, startup time, role, optional
`project_name`, selected sources, and endpoints. Discovery checks `capabilities`
and accepts a descriptor only when the recorder reports the same PID and token.

`capabilities_result` and `status_snapshot_result` both include an `instance`
object with that identity. Request payloads remain unchanged: a client selects
an endpoint before sending its request.

## Daemon endpoints

On macOS and Linux, recs owns these Unix sockets:

- `~/.local/state/recs/control.sock` for requests
- `~/.local/state/recs/events.sock` for subscriptions

On Windows, it owns these named pipes:

- `\\.\pipe\recs-control`
- `\\.\pipe\recs-events`

Clients should call `recs.daemon.paths.external_control_endpoint()` and
`external_event_endpoint()` instead of duplicating these paths.

The API is local only. recs does not open a TCP port or provide authentication
or network transport.

## Versions

There are two independent versions:

- `reccy.protocol.rpc.VERSION` is the transport version. It is currently `1` and is
  exchanged during every connection handshake.
- `recs.daemon.gui_protocol.VERSION` is the recs payload version. It is
  currently `11` and is returned by `capabilities`.

A client normally does not need to import either constant because
`reccy.protocol.rpc.Client` handles the transport handshake and `capabilities` reports
the payload version.

## Commands

The `capabilities` response is the authoritative list of commands supported by
the selected recorder. Commands in the following table that do not have a data
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
| `new_session` | none | `new_session_started` |
| `card_replace` | none | `card_replace_started` |
| `pause_recording` | none | `"ok"` |
| `resume_recording` | none | `"ok"` |
| `play_session` | optional `session: negative int`, `source: str`, `channel: "N" \| "N-N"`, `output_channel: "N" \| "N-N"` | `playback_state` |
| `stop_playback` | none | `playback_state` |
| `pause_playback` | none | `playback_state` |
| `continue_playback` | none | `playback_state` |
| `jump_playback` | `seconds: float` | `playback_state` |
| `jump_session` | `offset: -1 \| 1` | `playback_state` |
| `reload_profiles` | none | `"ok"` |
| `switch_project` | optional `project_name: str | null` | `project_switched` |
| `add_musician` | `musician: Musician` | `musician` |
| `list_musicians` | none | `musicians` |
| `edit_musician` | `nickname: str`, optional replacement lists and clear flags | `musician` |
| `delete_musician` | `nickname: str` | `musician_removed` |
| `assign_musician` | `nickname: str`, `source: str`, `channels: list[int]`, optional `track_name: str | bool` | `musician_assignment` |
| `remove_musician` | `nickname: str`, optional `source: str`, optional `channels: list[int]` | `musician_assignment_removed` |
| `subscribe_waveforms` | none | `waveform_subscription` |
| `unsubscribe_waveforms` | none | `waveform_subscription` |
| `shutdown` | none | `"ok"` |

### Capabilities

Call this first when a client needs to adapt to different recs versions:

```json
{
  "type": "capabilities_result",
  "commands": ["calibrate", "capabilities", "disk_status"],
  "version": 11
}
```

The real `commands` list contains every command supported by that daemon; the
example is abbreviated.

### Project switching

`switch_project` moves a running recorder to an independent mutable workspace.
Pass a project name to use or create a named project. Pass `null`, or omit the
parameter, to return to the default workspace:

```python
result = client.call('switch_project', project_name='x18-show')
default_result = client.call('switch_project')
```

Before switching, recs saves the current configuration, track layout, track
names, musicians, and musician assignments in the current workspace. An
existing target loads its saved mutable state. A missing named project is
created from the current workspace. Subsequent mutations are written to the
target workspace, never to the workspace that was left.
When capture is active, switching closes the current session and starts a new
session under the target project's directory.

The response identifies the active workspace and its settings file:

```json
{
  "type": "project_switched",
  "project_name": "x18-show",
  "created": false,
  "settings_path": "/home/me/.config/recs/daemon-project-settings/x18-show.json"
}
```

For the default workspace, `project_name` is `null` and `settings_path` is the
daemon's global `daemon-settings.json`. Foreground user settings remain in
`settings.json`, and user project settings remain in `project-settings/`; the
daemon has independent `daemon-project-settings/` and `daemon-projects/`
workspaces. Project switching requires saved settings to be enabled. The
recorder also updates its instance descriptor and writes a
`project_switched` event to the session record.

### Status

`status_snapshot` returns the complete current state needed by a monitoring
client:

```json
{
  "type": "status_snapshot_result",
  "devices": [],
  "disk": {
    "free_bytes": 700000000000,
  "path": "/mnt/openloop/recs/-default-/2026/08/28/12-00-00/session-record.jsonl",
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
  "record_path": "/mnt/openloop/recs/-default-/2026/08/28/12-00-00/session-record.jsonl",
  "midi": [],
  "osc": [],
  "playback": {"state": "waiting"},
  "recording": {"paused": false},
  "rows": [],
  "session_directory": "/mnt/openloop/recs/-default-/2026/08/28/12-00-00"
}
```

The fields have these meanings:

| Field | Meaning |
| --- | --- |
| `devices` | Configured audio sources, including channel count, sample rate, and whether each source is online |
| `disk` | The same object returned by `disk_status`, without its `type` field |
| `errors` | Recorded errors, each with `timestamp`, `message`, and optional boolean `value` |
| `record_path` | Absolute path of the current session record |
| `midi` | Current MIDI input states |
| `osc` | Current OSC recorder states |
| `playback` | Current recorded-audio transport state, without its `type` field |
| `recording.paused` | Whether recording is globally paused |
| `rows` | The current live-display rows described under Events |
| `session_directory` | Absolute path of the current session directory |

`disk_status` returns filesystem usage for the current record path, or its
nearest existing ancestor when the record does not exist yet:

```json
{
  "type": "disk_status_result",
  "free_bytes": 700000000000,
    "path": "/mnt/openloop/recs/-default-/2026/08/28/12-00-00/session-record.jsonl",
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

`estimated_seconds_remaining` is `null` until recs has measured a nonzero
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
addresses returned by `mutable_attributes`. recs validates and coerces the new
value, applies it to active source processes, records the change in the
record, and saves it when `save_settings` is enabled.

Physical configuration fields also accept unit strings. For example,
`set_cfg(address="recording.longest_file_time", value="1h")` stores and returns
`3600.0` seconds. Bare numbers retain their existing units. Disk threshold lists
normalize to byte-count or second strings. See
[Configuration Units](configuration-units.md) for supported fields and validation.
This does not change timestamps, status payloads, or waveform frame counts.

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

### Musicians

`add_musician` stores a musician under its unique `nickname`. A musician has
zero or more `names`, `public_keys`, and `links`, plus an optional
`copyright_name`. Links are opaque strings, so values such as `insta:mike`,
`mike@insta`, `mailto:mike@example.com`, telephone numbers, and web links are
all retained unchanged:

```python
client.call(
    'add_musician',
    musician={
        'nickname': 'mike',
        'names': ['Michael'],
        'public_keys': ['ssh-ed25519 AAA...'],
        'links': ['insta:mike'],
    },
)
```

`list_musicians` returns every stored record in nickname order:

```json
{
  "type": "musicians",
  "musicians": {
    "mike": {
      "nickname": "mike",
      "names": ["Michael"],
      "public_keys": ["ssh-ed25519 AAA..."],
      "links": ["insta:mike"]
    }
  }
}
```

`recs control musician-list` prints the `musicians` object as TOML, with the
nicknames under its top-level `musicians` table.

`edit_musician` changes only list fields supplied by the request. Supplying a
list replaces that list. `clear_names`, `clear_public_keys`, and `clear_links`
explicitly clear their respective lists; a request cannot
both set and clear the same field. `delete_musician` removes the musician and
every assignment that refers to it.

`assign_musician` assigns a musician to one or more one-based channels on an
online source. recs permits only one musician per source. Repeating an
assignment for that musician adds channels; assigning another musician to the
same source fails until the existing assignment is removed:

```python
client.call(
    'assign_musician',
    nickname='mike',
    source='Ext',
    channels=[1, 2],
    track_name=True,
)
```

`track_name` controls labels for complete configured tracks included in the
assignment. `false` leaves labels unchanged. `true` uses the track channels
and nickname, so channels 1-2 for `tom` become `1-2 + tom`; a string replaces
the nickname in that form.

`remove_musician` with `source` and no `channels` removes that musician from
every assigned channel of that source. With neither `source` nor `channels`,
it removes every source assignment for the musician. The musician record is
retained in both cases.

Musician records and assignments are saved with the active settings when
`save_settings` is enabled. Assignment data belongs to settings and session
records, never to a musician record. A session header snapshots the current
assignment map, and later add, edit, delete, assign, and removal commands are
written as session events.

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
levels and the per-source noise floors that recs applied:

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

`new_session` ends the current session and starts another without stopping
capture. recs closes the current media files and session record, creates a new
session directory under the configured output directory, and starts a new
session record with a new session ID. The response identifies both records:

```json
{
  "type": "new_session_started",
  "session_id": "8e9161e7-2890-46af-b45f-9d7186374462",
  "session_directory": "/mnt/openloop/recs/-default-/2026/09/07/18-30-00",
  "previous_record_path": "/mnt/openloop/recs/-default-/2026/09/07/17-00-00/session-record.jsonl",
  "record_path": "/mnt/openloop/recs/-default-/2026/09/07/18-30-00/session-record.jsonl"
}
```

The old record contains a `session_continued_at` entry pointing to the new
record, and the new record header uses `continued_from` to point back to the
old record. Both links are relative to the record containing them.

Audio input remains open during the transition. recs temporarily queues input
blocks while it closes the old files and opens the new files, then drains them
in order. Each device keeps its existing timeline, so the first audio file in
the new session continues the device's sample index from the old session.
MIDI messages and OSC packets received during the transition are likewise
retained and written to the new session.

### Card replacement

`card_replace` prepares recs for replacing the removable card that contains
the current output directory. It is intended for a machine with a single card
reader: send the command before removing the old card, then insert the new
one in the same reader.

The command closes and syncs every active audio, MIDI, and OSC file and
record on the old card, records the old card's filesystem UUID in those
records, and leaves the card mounted. Capture continues, but recs holds
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

recs polls mounted recording disks every
`recording.card_replace_poll_seconds` (default `1`) for a disk whose UUID
differs from `old_uuid` and has at least the configured removable-disk
emergency reserve free. If such a disk is already mounted when replacement
begins, recs switches immediately. On finding one, it creates a new session
directory on that disk, writes the retained audio blocks, MIDI messages, and
OSC packets to their new session files, and then writes newly received data
normally. The configured output directory is not changed or saved: recs applies
the relative path from the old card's mount point to the new card's mount point
for this session only.

While recs is waiting for a replacement card, `rows` events and
`status_snapshot` include an error record with `message` set to `"awaiting
card"` and `value` set to `true`. When recs finds a destination card, that
same record has `value` set to `false`.

If no different UUID appears within
`recording.card_replace_timeout_seconds` (default `300`), recs resumes on the
old card only when that card is still mounted. It creates a new session
directory there before draining all retained media.

The retained audio backlog is bounded by
`recording.audio_buffer_seconds` and the memory reserve. Once a source buffer
fills, recs drops subsequent frames and records the existing `buffer_overflow`
information when recording resumes. Set `audio_buffer_seconds` high enough for
the expected physical card-change time and the available memory.
`card_replace` fails without changing recording when the current output
directory is not on a mounted recording disk with a discoverable filesystem
UUID.

`pause_recording` closes active audio recordings and prevents further audio
recording. `resume_recording` clears that global pause, allowing audio sources
to begin writing new files. MIDI and OSC recording continue while audio is
paused. Both transitions are recorded in the record.

Use `status_snapshot` to read the resulting `recording.paused` state.

### Recorded-audio transport

`play_session` stops audio capture and plays one audio stream from a finalized
`recording.toml`. Its default `session` is `-1`, the most recently started
session; `-2` selects the one before it. A session number must be negative.

`source` accepts either the recorded source name or source ID. `channel` and
`output_channel` each accept a one-based mono channel such as `9`, or an
adjacent pair such as `9-10`. A selected input and output must have the same
width. The output is the operating system default output device.

When no source or channel is supplied, recs selects the recorded source with
the highest numbered input and then its highest numbered stereo pair. If no
`output_channel` is supplied, it selects the highest mono channel or adjacent
stereo pair available on the default output device. Playback supports recorded
mono streams and stereo pairs.

Playback preserves the stream's timeline: recorded gaps are silence. It ends
at the session's recorded end and resumes audio capture only if playback paused
it. `stop_playback` follows the same rule. A manual or disk-space pause before
or during playback remains in force afterwards. An explicit `resume_recording`
stops playback and closes its output before allowing capture to resume.
`pause_playback` holds the playback position;
`continue_playback` resumes it. `jump_playback` moves by signed seconds,
clamped to the session's beginning and end. `jump_session` accepts `-1` or
`1`, selecting the preceding or following session while retaining the source,
channel, and output selection.

Every transport command returns this state shape:

```json
{
  "type": "playback_state",
  "state": "playing",
  "session": -1,
  "path": "/recordings/-default-/2026/09/04/15-01-57/recording.toml",
  "source": "Mixer",
  "channel": "9-10",
  "output_channel": "3-4",
  "position_seconds": 12.5,
  "duration_seconds": 3742.25
}
```

`state` is `waiting`, `playing`, or `paused`. In `waiting`, all selection and
position fields are `null`. A playback file or output-device failure records a
warning and ends playback after closing its output. The recorder thread then
resumes audio capture only if playback owns the recording pause.

`mark` appends a labeled event to the current record. `set_key_label`
updates the label associated with a recorded key. `reload_profiles` reloads the
configured profiles file and fails if recs was not started with a profiles
path. The entire replacement is validated before any configuration changes.
Changes to startup-only settings, including audio formats and sample types,
reject the whole reload; restart recording to apply those changes. A successful
reload queues mutable settings to live source processes. The session record's
`profiles_reloaded` revision is acknowledged by each child's existing
`cfg_applied` event; the command response does not wait for those acknowledgments.

## Live waveforms

Waveforms use both public endpoints. Start an `EventClient` first, then call
`subscribe_waveforms` on the control endpoint:

```python
from reccy.protocol import rpc

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
`reccy.protocol.rpc.EventClient`:

```python
from reccy.protocol import rpc

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

The bundled terminal client performs this subscription and displays the live
rows, warnings, buffer pressure, dropped frames, card-replacement state, and an
estimated disk-space countdown:

```console
recs watch
recs watch --json
```

The JSON form writes the initial `status_snapshot` followed by each public event
as one JSON object per line. Neither form starts a recorder or polls the selected
recorder.

recs publishes these events:

| Event | Data |
| --- | --- |
| `rows` | `rows` live-display records and current `errors` |
| `playback_state` | A `playback_state` object without its `type` field, published when playback starts or returns to waiting |
| `waveform_layout` | Current track layout and waveform generation for one source |
| `waveform` | One min/max envelope batch for one source |
| `shutdown` | empty; recs has begun shutting down |
| `stopped` | empty; the reccy service lifecycle has stopped |

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

Before closing event subscriptions, recs publishes one `shutdown` event and
then the reccy lifecycle publishes one `stopped` event.

## Errors and limits

Errors use this wire shape:

```json
{"type":"error","message":"explanation"}
```

`reccy.protocol.rpc.Client` converts this to `ConnectionError(message)`. Raw clients
must decode it themselves.

Only one control request may be awaiting the recs recorder at a time. A second
request receives `recs already has an active control client`.

recs waits at most five seconds for the recorder loop to answer an external
request. The reccy client has its own timeout, which defaults to one second;
choose a timeout appropriate for the command. A client timeout closes only the
client connection and does not cancel a command that the recorder has already
received.

The current calibration implementation can wait up to 15 seconds internally,
which is longer than the external five-second response limit. A slow
calibration can therefore return a timeout even though processing continues in
the recorder. This is a current protocol limitation.

The reccy transport allows at most 64 KiB in one request and requires the
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
is a reccy `event` object until the client or server closes the connection.
