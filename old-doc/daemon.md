# Startup and daemon plan

## Goal

Make `recs` installable as a long-running recorder that starts automatically and
keeps running on Windows, macOS, and Linux.

The practical target is a per-user background recorder, not a machine-wide system
daemon. Audio devices, microphone permissions, output paths, and desktop-session
privacy rules are all user-scoped on modern operating systems. A system service is
the wrong default for recording from normal input devices.

## User-facing behavior

Add a small service-management interface:

```sh
recs daemon install [recs options...]
recs daemon uninstall
recs daemon start
recs daemon stop
recs daemon restart
recs daemon status
```

The installed service should:

1. Start automatically for the current user.
2. Run `recs` without a terminal UI.
3. Restart if it crashes.
4. Write logs to a predictable per-user log directory.
5. Preserve the exact recording options supplied at install time.
6. Refuse to install if the selected configuration cannot run unattended.

The default installed command should include:

```sh
recs --silent
```

The user can add normal recording options during install:

```sh
recs daemon install --include "MacBook Pro Microphone" --output ~/Recordings
```

## Definitions

Use these names consistently:

- `daemon` means the long-running installed recorder feature.
- `service` means the native operating-system startup mechanism.
- `install` means write the native service definition and enable autostart.
- `uninstall` means stop the service, disable autostart, and remove the service definition.
- `status` means report whether the native service exists and whether it is running.

## Platform strategy

### macOS

Use a per-user LaunchAgent.

Install location:

```text
~/Library/LaunchAgents/com.swirly.recs.plist
```

Use:

- `RunAtLoad`: true
- `KeepAlive`: true
- `ProgramArguments`: installed `recs` executable plus saved options
- `StandardOutPath`: `~/Library/Logs/recs/recs.out.log`
- `StandardErrorPath`: `~/Library/Logs/recs/recs.err.log`

Do not use a LaunchDaemon by default. LaunchDaemons run outside the normal user
session and are a poor fit for microphone access and per-user audio devices.

Operational commands:

```sh
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.swirly.recs.plist
launchctl bootout gui/$UID ~/Library/LaunchAgents/com.swirly.recs.plist
launchctl print gui/$UID/com.swirly.recs
```

Key macOS concerns:

1. Microphone permission must be granted to the executable host that macOS
   attributes audio access to.
2. The service should document how to run once interactively before installing if
   microphone permission has not been granted yet.
3. The LaunchAgent should not request the GUI display.
4. The installer should fail if `--gui` is present.

### Linux

Use a per-user systemd service when systemd is available.

Install location:

```text
~/.config/systemd/user/recs.service
```

Unit shape:

```ini
[Unit]
Description=recs background recorder
After=default.target

[Service]
ExecStart=/absolute/path/to/recs --silent ...
Restart=always
RestartSec=5
WorkingDirectory=%h
StandardOutput=append:%h/.local/state/recs/recs.out.log
StandardError=append:%h/.local/state/recs/recs.err.log

[Install]
WantedBy=default.target
```

Operational commands:

```sh
systemctl --user daemon-reload
systemctl --user enable recs.service
systemctl --user start recs.service
systemctl --user status recs.service
systemctl --user stop recs.service
systemctl --user disable recs.service
```

Do not install a root system service by default. PipeWire and PulseAudio are
normally per-user services, so a root service is unlikely to see the same audio
devices as an interactive `recs` invocation.

If the user wants recording to start before login, document the tradeoff and make
them opt into:

```sh
loginctl enable-linger "$USER"
```

Fallback for non-systemd Linux:

1. Support XDG autostart with a `.desktop` file.
2. Make clear that it starts at desktop login and has weaker restart behavior.

### Windows

Use Task Scheduler by default, not a Windows Service.

Reason: Windows Services run in Session 0 and often cannot access the same
interactive audio devices, user profile, and microphone permissions as a normal
desktop process. A per-user scheduled task at logon is a better default.

Task shape:

- Task name: `recs`
- Trigger: at logon for the current user
- Action: installed `recs.exe` plus saved options
- Restart on failure: enabled
- Run only when user is logged on: true
- Working directory: user profile or configured output directory
- Log files: `%LOCALAPPDATA%\recs\logs\`

Operational commands can be implemented through PowerShell:

```powershell
Register-ScheduledTask
Unregister-ScheduledTask
Start-ScheduledTask
Stop-ScheduledTask
Get-ScheduledTask
```

Do not install a Windows Service by default. If a true service is ever needed,
make it a separate explicit mode because it will need additional design for
Session 0, permissions, and audio-device visibility.

## Installed command rules

The daemon installer should reject options that require interactivity:

- `--gui`
- live terminal display options
- calibration modes that print transient output instead of recording
- informational commands such as `--info` or `--types`

The daemon installer should allow normal recording options:

- device selection
- output directory
- file format
- recording thresholds
- key recording only if it works unattended on the platform

The installer should resolve the executable path at install time. Do not write a
bare `recs` command into native service files because launch environments often
have a smaller `PATH` than an interactive shell.

## Configuration persistence

Store daemon install metadata in a per-user config file:

macOS and Linux:

```text
~/.config/recs/daemon.json
```

Windows:

```text
%APPDATA%\recs\daemon.json
```

The file should contain:

```json
{
  "version": 1,
  "argv": ["--silent", "--include", "MacBook Pro Microphone"],
  "executable": "/absolute/path/to/recs",
  "platform": "macos"
}
```

Native service definitions should be regenerated from this file during reinstall
or upgrade.

## Logging

Use per-user log directories.

macOS:

```text
~/Library/Logs/recs/
```

Linux:

```text
~/.local/state/recs/
```

Windows:

```text
%LOCALAPPDATA%\recs\logs\
```

The logs should capture:

1. Service startup command.
2. Effective config.
3. Selected devices.
4. Warnings.
5. Unhandled exceptions.
6. Clean shutdown.

Do not rely only on native service logs. Write application logs too, because users
need one predictable place to look across platforms.

## Process behavior

The long-running recorder should:

1. Handle `SIGTERM` and platform shutdown signals cleanly.
2. Flush open audio files before exit.
3. Write the session manifest before exit.
4. Avoid curses or GUI output.
5. Avoid prompting for input.
6. Recover when devices disappear and reappear.
7. Keep output paths deterministic and per session.

The native service manager handles process restart. `recs` should not implement
its own outer restart loop.

## Python packaging concerns

The installed service needs a stable executable path.

Preferred approach:

1. Install `recs` into a dedicated `uv tool` or virtual environment.
2. Resolve the actual executable path during `recs daemon install`.
3. Store that absolute path in daemon metadata.
4. Regenerate service files after reinstalling or upgrading `recs`.

Do not point service files at a repository checkout unless the user explicitly asks
for development-mode installation.

## Implementation plan

### 1. Add daemon model objects

Add small pydantic models for:

- daemon metadata
- platform service definition
- install result
- status result

Keep these models independent from audio recording code.

### 2. Add platform-specific renderers

Create one renderer per platform:

- macOS LaunchAgent plist
- Linux systemd user unit
- Linux XDG autostart fallback
- Windows scheduled task PowerShell commands

Renderer tests should be regression tests over generated files or command data.
They should not install real services.

### 3. Add platform-specific service controllers

Add controllers for:

- install
- uninstall
- start
- stop
- restart
- status

Unit tests should mock subprocess calls and assert the generated commands.
Do not unit-test the operating system service managers themselves.

### 4. Add CLI commands

Add:

```sh
recs daemon install
recs daemon uninstall
recs daemon start
recs daemon stop
recs daemon restart
recs daemon status
```

The install command should accept the same recording options as `recs`, validate
that they are daemon-safe, then save them.

### 5. Add integration documentation

Document:

1. How to install the daemon.
2. How to view logs.
3. How to uninstall.
4. How to handle microphone permissions.
5. Why per-user startup is the default.

### 6. Manual platform verification

After unit tests pass, manually verify on each platform:

macOS:

1. Install LaunchAgent.
2. Start it.
3. Confirm it records audio.
4. Confirm it restarts after kill.
5. Uninstall it.

Linux:

1. Install systemd user service.
2. Start it.
3. Confirm it records audio through the user's audio server.
4. Confirm restart on failure.
5. Uninstall it.

Windows:

1. Install scheduled task.
2. Log out and back in.
3. Confirm it records audio.
4. Confirm failure restart behavior.
5. Uninstall it.

## Testing plan

Unit tests:

1. Render macOS plist.
2. Render Linux systemd unit.
3. Render Linux XDG autostart file.
4. Render Windows scheduled-task command data.
5. Validate daemon-safe options.
6. Validate rejected interactive options.
7. Validate daemon metadata round trip.

Regression tests:

1. Snapshot generated LaunchAgent plist.
2. Snapshot generated systemd service.
3. Snapshot generated XDG autostart file.
4. Snapshot generated daemon metadata.

No test should require actually installing a system service.

## Open decisions

1. Should daemon management live under `recs daemon ...` or a separate
   `recsctl` command?
2. Should install require an explicit `--output`, or should the current default
   session directory behavior be allowed?
3. Should the daemon run one endless session, or should it rotate sessions daily?
4. Should there be a separate `recs daemon logs` command?
5. Should Windows offer an advanced real-service mode later?

## Non-goals

1. Do not make the GUI run as a daemon.
2. Do not install root services by default.
3. Do not solve cloud sync or remote monitoring.
4. Do not implement a custom supervisor inside `recs`.
5. Do not add a new dependency unless the native platform tools are insufficient.
