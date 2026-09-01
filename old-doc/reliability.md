# Reliability scan

This scan covers running `recs` as a daemon, a normal command-line program, and a
frozen GUI app. The main risks are local process and IPC reliability issues, not
network reliability. Current GUI IPC is local-only.

## Highest priority issues

### Frozen app execution is likely fragile

These paths assume `sys.executable -m ...` works:

- `recs/ui/gui_process.py` launches `python -m recs.ui.gui_child`.
- `recs/cfg/device.py` runs `python -m recs.base._query_device`.

In a frozen app, `sys.executable` is usually the app binary, not a Python
interpreter that can run `-m recs...`. This is a likely failure point for GUI
child startup and device probing.

### Multiprocessing in a frozen app may need explicit support

`SourceProcess` uses `multiprocessing.Process(target=SourceRecorder, ...)`.
Frozen Windows and macOS apps often need `multiprocessing.freeze_support()` very
early in `__main__`, and sometimes a different child-process entry strategy.

### A source process can hang without being detected

The recorder detects a lagging device only after receiving updates. If a source
process stays alive but stops sending updates, the main loop can continue
forever waiting with timeouts. This is especially relevant for daemon mode.

Existing protection handles:

- process exits unexpectedly;
- source sends updates but falls behind real time.

It does not fully handle:

- process alive, no updates, no EOF.

### Device probing can hang startup

`device.query_devices()` runs a subprocess with `subprocess.run(..., check=True)`
but no timeout. Also, `Recorder.__init__` calls `self.poller.poll()`
synchronously before the background poller starts. If device probing hangs,
startup hangs.

### Daemon metadata writes are not atomic

`ServiceController._write_metadata()` writes directly to the final metadata path.
If a client runs `recs --gui` while metadata is partially written,
`load_metadata()` treats it as invalid and falls back to local recording. That
can start a second recorder instead of attaching to the daemon.

### Daemon/client version mismatch is not handled

The protocol has `hello.version`, but the daemon currently ignores it. There is
no server response, no version rejection, no capability negotiation, and no
compatibility check against daemon metadata.

Row payloads are loose enough that many minor changes may work. Incompatible
changes will likely fail silently or cause stale or empty GUI behavior.

## Medium priority issues

### Local GUI child JSON handling is brittle

`recs/ui/gui_child.py` does raw `json.loads(line)` in its reader thread. One
malformed line can kill that thread, leaving the GUI stale. Remote GUI IPC is
better because malformed messages are caught and ignored.

### Windows named-pipe connect may hang

The Unix socket client has a timeout. The Windows pipe client uses
`multiprocessing.connection.Client(endpoint, family='AF_PIPE')` without an
explicit timeout. If Windows named-pipe connection attempts block when the daemon
is wedged or half-started, `recs --gui` may hang instead of falling back.

### IPC server failure causes ambiguous fallback behavior

If the daemon cannot bind its socket or pipe, it logs and continues recording. A
later `recs --gui` will fail to attach and fall back to local recording. That
preserves recording, but can accidentally start a second recorder.

### GUI IPC accept thread is not joined

The accept loop runs in a daemon thread. This is probably acceptable for process
shutdown, but it makes clean shutdown less deterministic, especially around
closing sockets or pipes while `accept()` is blocked.

### Child process failures can be too quiet

If a `SourceRecorder` child dies because of file I/O, sounddevice, or soundfile
errors, the parent usually sees only that the process exited. For hardware
sources it marks the device failed, but error details are not propagated into the
record or user-visible daemon state.

### Device config JSON is all-or-nothing

Misformatted device JSON or empty device JSON fails configuration. That is
probably acceptable for a config file, but it is not resilient.

For line-oriented IPC:

- remote daemon/client protocol ignores malformed lines;
- local GUI child stdin can lose its reader thread on malformed JSON;
- GUI process stdout key events ignore malformed lines.

## Lower priority issues and design tradeoffs

### No durable daemon status or error state yet

If the daemon is running but GUI IPC is broken, the user has to infer it from
logs or behavior. There is no status file saying "recording, but GUI IPC failed
to bind".

### No stale endpoint metadata validation beyond connectability

`recs --gui` trusts metadata if the endpoint connects. That is usually fine
locally, but there is no check that the process behind the endpoint is actually
compatible `recs`.

### Fixed per-user endpoint means only one daemon can own GUI IPC

That is intended, but if two daemon instances are accidentally started, one will
fail IPC and keep recording silently.

## Suggested fix order

1. Add frozen-app entry handling:
   - `multiprocessing.freeze_support()` in `__main__`;
   - replace `sys.executable -m ...` helpers with explicit app subcommands or
     frozen-aware dispatch.
2. Add source heartbeat/stall detection:
   - track last update time per source;
   - stop/restart or mark failed if alive but silent too long.
3. Make daemon metadata atomic:
   - write a temporary file;
   - fsync if practical;
   - rename into place.
4. Add protocol handshake/version response:
   - client sends hello;
   - daemon replies hello/version;
   - incompatible client closes with a visible error instead of showing stale
     GUI.
5. Harden local GUI child JSON parsing:
   - catch `json.JSONDecodeError`;
   - ignore bad lines like the remote IPC path.
6. Add Windows pipe connection timeout or nonblocking fallback behavior if
   practical.

