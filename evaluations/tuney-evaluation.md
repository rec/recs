# tuney evaluation

## Summary

I scanned representative runtime paths in `tuney`, with emphasis on audio
playback/recording, GUI shutdown, and help rendering. I also used the existing
memory note that QWebEngine help rendering previously crashed in this project,
so I treated GUI rendering changes as release-sensitive. I did not modify the
project.

## Findings

### High: GUI close can be blocked by autosave or audio shutdown errors

`MainWindow.closeEvent()` saves autosave state and closes the player before
calling `super().closeEvent(event)` (`tuney/ui/main_window.py:173-176`). If
autosave or `state.player.close()` raises, the superclass close handling is not
called and the GUI may fail to close cleanly.

For a desktop app, close-event cleanup should usually protect the actual close
path with `try/finally`, while still logging cleanup failures.

### High: recording append does not validate the existing file format

`AudioFileWriter` opens an existing recording in `r+` mode when `append=True`
(`tuney/audio/output_file.py:17-31`) and appends raw blocks later. It does not
check that the existing file's sample rate and channel count match the current
stream.

If the user pauses/resumes or changes devices/settings between recording
segments, this can append incompatible audio into the same file or fail late
inside `soundfile`.

### Medium: stream shutdown assumes `stop()` is always valid

`AudioEngine.close()` calls `stream.stop()` and then `stream.close()` whenever a
cached stream exists (`tuney/audio/engine.py:90-97`). Some audio backends raise
when stopping an inactive, failed, or already-stopped stream. A close path
should be robust because it runs from GUI shutdown and error recovery.

### Medium: `wait()` can block indefinitely

`AudioEngine.wait()` waits on `playback_complete` with no timeout
(`tuney/audio/engine.py:105-108`). If the callback never sets the event because
the stream stalls, the device disappears, or no callback runs after a stop
request, callers can hang indefinitely.

### Medium: help Markdown supports links with unrestricted schemes

The fallback help renderer escapes text, then rewrites Markdown links into
`<a href="...">` tags and enables external links (`tuney/ui/help.py:20-24`,
`tuney/ui/help.py:64-67`). Since README content is local project content this
is not an immediate remote-input vulnerability, but a malicious or accidental
`javascript:`/custom-scheme link in bundled help would be opened by the GUI.

### Low: PortAudio errors are detected by class name in some paths

`Player.reconfigure_device()` and `Player.start()` catch broad exceptions and
compare `e.__class__.__name__` to `"PortAudioError"` (`tuney/audio/player.py:33-39`,
`tuney/audio/player.py:117-122`). This avoids importing `sounddevice` at module
load time, but it can suppress unrelated exceptions with the same class name or
miss wrapped backend errors.
