# External IPC plan

## Goal

Expose the existing Recs control protocol to other local processes through
`reccy.rpc`. The daemon owns the endpoints. Clients can make a request and
receive its response, or subscribe to live updates. There is no compatibility
mode for the current raw GUI socket protocol.

The GUI socket remains a private Recs GUI transport. The new endpoints are the
supported external API for Showco, Lyte, scripts, and future local clients.

## Transport

Use one Reccy RPC server with two per-user endpoints:

- control: `~/.local/state/recs/control.sock`
- events: `~/.local/state/recs/events.sock`

On Windows, use the corresponding named-pipe endpoint form accepted by
`reccy.rpc`. Endpoint construction belongs in `recs.daemon.paths`, not in
clients.

`reccy.rpc.VERSION` is the transport version. It is separate from
`recs.daemon.gui_protocol.VERSION`, which remains the version of the Recs
request and response payloads.

Every connection performs Reccy's hello handshake. A control connection carries
one `request` followed by its matching `response` and then closes. An event
connection sends `subscribe` after the handshake and remains open until either
side closes it.

## Control mapping

The Reccy request is a lossless envelope around one existing Recs request:

```json
{
  "type": "request",
  "id": "...",
  "command": "set_cfg",
  "params": {
    "address": "recording.longest_file_time",
    "value": 3600
  }
}
```

The adapter reconstructs the Recs message by combining `command` and `params`:

```json
{"type":"set_cfg","address":"recording.longest_file_time","value":3600}
```

It validates that message with `gui_protocol.MESSAGE`, then gives it to the
same `Recorder._handle_control_request` path used by the GUI. This includes all
current Recs commands, their validation, manifest events, source-recorder
configuration queuing, and typed response models.

`shutdown` is also accepted through the control endpoint. It begins the normal
Recorder shutdown once, returns the final `recording_state`, and does not add a
second shutdown path.

Successful RPC responses retain the full Recs response model, including its
`type`, in `result`:

```json
{
  "type": "response",
  "id": "...",
  "ok": true,
  "result": {
    "type": "cfg_set",
    "address": "recording.longest_file_time",
    "value": 3600
  }
}
```

Keeping `result.type` is required. Although the RPC envelope matches requests
by `id`, Recs clients still need the existing typed response to route and
interpret command-specific data.

Invalid Recs requests and Recs command failures return `ok: false` with the
existing error text in `message`. Transport, handshake, and malformed-RPC
errors remain Reccy IPC errors rather than Recs command responses.

## Events

Use the existing `rows` notification payload as the event data:

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

Publish this event at the same cadence as the daemon GUI row updates, using the
same row and error providers. Do not publish from the recorder's tight polling
loop. `status_snapshot` remains the request for a complete immediate snapshot.

When shutdown begins, publish one `shutdown` event before closing the event
server. Close all event subscriptions afterward. Duplicate shutdown requests
must not generate additional events.

## Implementation steps

1. Add a Recs-owned external IPC adapter in `recs.daemon.external_ipc`.
   It owns `rpc.Server`, converts `rpc.Request` values to
   `gui_protocol.Request | gui_protocol.Shutdown`, queues requests for the
   recorder loop, and converts typed Recs responses back to `rpc.Response`.
   Preserve the response model's `type` in `result`.
2. Construct the adapter only in daemon mode, start it with the recorder, and
   close it during recorder shutdown. If endpoint startup fails, record and
   expose a distinct external-IPC error in daemon status, log it, and continue
   recording without the external API, matching the GUI IPC failure behavior.
3. Extend the recorder loop to drain queued external requests beside GUI
   control requests. The RPC handler thread only waits for that result; it must
   not read devices, mutate recorder state, or write recording files.
4. Reuse `_handle_control_request` for every non-shutdown command. Route
   shutdown through the existing one-shot shutdown mechanism, publish its event
   once, and release any request currently waiting for a response as the server
   closes.
5. Move external row publication to the daemon GUI update cadence, or give both
   transports one shared status-publication method. It must produce identical
   `rows` and timestamped `errors` payloads for GUI and external subscribers.
6. Document the external endpoint, handshake, request envelope, response
   envelope, event subscription, error behavior, and shutdown behavior in
   `doc/recs_protocol.md`. Remove documentation that describes the raw GUI
   endpoint as the public daemon API.
7. Add focused tests for endpoint paths, request mapping, a successful typed
   result, an invalid Recs command, one `rows` event, shutdown delivery, and
   startup failure that leaves recording usable. Keep Reccy's transport tests
   in Reccy and test only the Recs adapter here.

## Completion criteria

- A local client using `reccy.rpc.Client` can call every documented Recs
  command without importing GUI IPC code.
- A subscribed `reccy.rpc.EventClient` receives Recs `rows` events with the
  same error records displayed by the daemon GUI.
- Responses preserve the existing Recs response type and fields.
- No external request handler performs recording work outside the recorder
  loop.
- Shutdown occurs once and closes GUI listeners, RPC event subscribers, and the
  external control service.
- The raw GUI socket is no longer described as the public external API.

## Additional work beyond the prompt

None.
