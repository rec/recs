"""Session selection and transport state for recorded-audio playback."""

from collections.abc import Callable
from pathlib import Path

from ufor.recording import AudioStream

from recs.audio.playback import (
    PlaybackRunner,
    PlaybackTimeline,
    default_output_channels,
    parse_channels,
    select_stream,
)
from recs.base.errors import RecsError
from recs.daemon import gui_protocol
from recs.recording.read import read_recording


class PlaybackControl:
    def __init__(
        self,
        recordings_root: Callable[[], Path],
        pause_recording: Callable[[], None],
        resume_recording: Callable[[], None],
        publish: Callable[[gui_protocol.PlaybackState], None],
        warning: Callable[[str], None],
    ) -> None:
        self.recordings_root = recordings_root
        self.pause_recording = pause_recording
        self.resume_recording = resume_recording
        self.publish = publish
        self.warning = warning
        self.runner: PlaybackRunner | None = None
        self.session_paths: list[Path] = []
        self.session_index: int | None = None
        self.path: Path | None = None
        self.source: str | None = None
        self.channel: str | None = None
        self.output_channel: str | None = None

    def play(self, request: gui_protocol.PlaySession) -> gui_protocol.PlaybackState:
        paths = self._sessions()
        index = len(paths) + request.session
        if not 0 <= index < len(paths):
            raise RecsError(
                f'No session {request.session}; {len(paths)} session(s) available'
            )
        score_path = paths[index]
        score = read_recording(score_path)
        stream = select_stream(score, request.source, request.channel)
        output = (
            parse_channels(request.output_channel, 'output channel')
            if request.output_channel is not None
            else default_output_channels(len(stream.stream.channels))
        )
        if len(output) != len(stream.stream.channels):
            raise RecsError(
                'Output channel count must match the selected recorded channel count'
            )
        self.stop()
        self.session_paths = paths
        self.session_index = index
        self.path = score_path
        self.source = stream.source_name or stream.source_id
        self.channel = stream.track_name or _stream_channel(stream)
        self.output_channel = _channel_text(output)
        self.pause_recording()
        self.runner = PlaybackRunner(
            PlaybackTimeline(score_path.parent, score, stream),
            output,
            self._finished,
            self._failed,
        )
        self.runner.start()
        return self._publish()

    def stop(self) -> gui_protocol.PlaybackState:
        if self.runner is not None:
            self.runner.stop()
            self.runner = None
            self.resume_recording()
        return self._publish()

    def pause(self) -> gui_protocol.PlaybackState:
        if self.runner is None:
            raise RecsError('No playback is active')
        self.runner.pause()
        return self._publish()

    def resume(self) -> gui_protocol.PlaybackState:
        if self.runner is None:
            raise RecsError('No playback is active')
        self.runner.resume()
        return self._publish()

    def jump(self, seconds: float) -> gui_protocol.PlaybackState:
        if self.runner is None:
            raise RecsError('No playback is active')
        self.runner.jump(seconds)
        return self._publish()

    def jump_session(self, offset: int) -> gui_protocol.PlaybackState:
        if self.session_index is None:
            raise RecsError('No session is selected for playback')
        target = self.session_index + offset
        if not 0 <= target < len(self.session_paths):
            raise RecsError('Requested session is outside the available range')
        return self.play(
            gui_protocol.PlaySession(
                type='play_session',
                session=target - len(self.session_paths),
                source=self.source,
                channel=self.channel,
                output_channel=self.output_channel,
            )
        )

    def state(self) -> gui_protocol.PlaybackState:
        if self.runner is None:
            return gui_protocol.PlaybackState(type='playback_state', state='waiting')
        return gui_protocol.PlaybackState(
            type='playback_state',
            state='paused' if self.runner.paused else 'playing',
            session=(self.session_index or 0) - len(self.session_paths),
            path=str(self.path),
            source=self.source,
            channel=self.channel,
            output_channel=self.output_channel,
            position_seconds=self.runner.seconds,
            duration_seconds=self.runner.timeline.duration,
        )

    def _sessions(self) -> list[Path]:
        root = self.recordings_root()
        records = (
            [root / 'recording.toml']
            if (root / 'recording.toml').is_file()
            else list(root.glob('**/recording.toml'))
        )
        sessions = [
            (read_recording(path).body.started_at or '', path) for path in records
        ]
        if not sessions:
            raise RecsError(f'No finalized sessions under {root}')
        return [path for _, path in sorted(sessions)]

    def _finished(self) -> None:
        self.runner = None
        self.resume_recording()
        self._publish()

    def _failed(self, message: str) -> None:
        self.warning(f'Playback stopped: {message}')
        self._finished()

    def _publish(self) -> gui_protocol.PlaybackState:
        state = self.state()
        self.publish(state)
        return state


def _channel_text(channels: tuple[int, ...]) -> str:
    return '-'.join(str(channel) for channel in channels)


def _stream_channel(stream: AudioStream) -> str:
    return '-'.join(channel.rsplit('-', 1)[-1] for channel in stream.stream.channels)
