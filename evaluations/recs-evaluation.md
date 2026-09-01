# recs evaluation

## Summary

I scanned representative `recs` runtime paths, especially audio file writing,
source process updates, and daemon service control. I also checked the repo
instructions and existing memory around daemon user communication. I did not
modify the project.

## Findings

### High: lost-time detection appears to use the wrong timestamp sign

`ChannelWriter._receive_block()` computes `dt = self.timestamp - timestamp`,
then updates `self.timestamp = timestamp` (`recs/audio/channel_writer.py:165-173`).
For normal increasing timestamps, `dt` is negative, so the
`dt > expected_dt * BLOCK_FUZZ` gap check will not fire after the first block.

The intended check appears to be detecting a large forward jump in input time.
As written, a sleep, stall, or dropped callback can be bridged into the current
recording instead of closing the file at the gap.

### High: short deleted files remain in `files_written`

`ChannelWriter._open()` extends `self.files_written` as soon as files are opened
(`recs/audio/channel_writer.py:150-155`). `_close()` later deletes files shorter
than `shortest_file_time` (`recs/audio/channel_writer.py:129-138`), but it does
not remove those paths from `files_written`.

That can make file counts, file-size state, source updates, or records refer
to files that were subsequently deleted.

### Medium: source process constructor performs the recording loop

`SourceRecorder.__init__()` creates the input stream and then immediately enters
the recording loop (`recs/ui/source_recorder.py:62-80`). Doing substantial I/O
inside `__init__` makes construction blocking and makes errors look like
construction failures rather than run failures.

This may match how `SourceProcess` starts child work, but it is a maintenance
risk because the class is shaped like a runtime object while its constructor
does most of the running.

### Medium: daemon status can report running when only a service command succeeds

`ServiceController.status()` reports `running=result.returncode == 0`
(`recs/daemon/controllers.py:124-153`). That is reasonable for
`systemctl is-active`, but it is weaker for commands such as macOS
`launchctl print` and Windows `Get-ScheduledTask`, where command success can
mean the service/task exists rather than that the recorder is actively running.

The status model may need platform-specific parsing of the actual state.

### Medium: macOS start/install uses `launchctl bootstrap` for both install and start

`install()` and `start()` both call `launchctl bootstrap` on macOS
(`recs/daemon/controllers.py:20-31`, `recs/daemon/controllers.py:79-88`).
If the LaunchAgent is already bootstrapped but stopped, `bootstrap` can fail
instead of starting it. A separate `kickstart` or enable/start path may be
needed for reliable restarts.

### Low: record track records use the first source channel as `track`

`SourceRecorder._new_files()` records `track=writer.track.channels[0]`
(`recs/ui/source_recorder.py:111-128`). For multi-channel tracks, this stores
only the first channel number rather than the configured track name or all
channels. That may make downstream records ambiguous.
