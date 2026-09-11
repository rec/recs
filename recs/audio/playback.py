"""Timed playback of a selected recorded audio stream."""

import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile
from ufor.recording import AudioFragment, AudioStream, RecordingScore

from recs.base.errors import RecsError


class PlaybackTimeline:
    """One recorded stream, read in its original timeline coordinates."""

    def __init__(self, root: Path, score: RecordingScore, stream: AudioStream) -> None:
        self.root = root
        self.score = score
        self.stream = stream
        self.rate = _rate(score, stream)
        self.channels = len(stream.stream.channels)
        self.end = stream.end
        self._assets = {asset.name: asset for asset in score.assets}
        self._fragments = _fragments(stream)

    @property
    def duration(self) -> float:
        return self.end / self.rate

    def read(self, start: int, frames: int) -> np.ndarray:
        output = np.zeros((frames, self.channels), dtype=np.float32)
        finish = start + frames
        for fragment in self._fragments:
            overlap_start = max(start, fragment.start)
            overlap_end = min(finish, fragment.start + fragment.count)
            if overlap_start >= overlap_end:
                continue
            if (asset := self._assets.get(fragment.asset)) is None:
                raise RecsError(f'Audio fragment has no asset: {fragment.asset}')
            path = self.root / asset.path
            with soundfile.SoundFile(path) as source:
                source.seek(fragment.asset_start + overlap_start - fragment.start)
                data = source.read(
                    overlap_end - overlap_start, dtype='float32', always_2d=True
                )
            if len(data) != overlap_end - overlap_start:
                raise RecsError(f'Audio payload is truncated: {path}')
            output[overlap_start - start : overlap_end - start] = data
        return output


class PlaybackRunner:
    """A worker which writes timeline blocks to the default output device."""

    def __init__(
        self,
        timeline: PlaybackTimeline,
        output_channels: tuple[int, ...],
        finished: Callable[[], None],
        failed: Callable[[str], None],
        *,
        block_frames: int = 2048,
    ) -> None:
        self.timeline = timeline
        self.output_channels = output_channels
        if len(output_channels) != timeline.channels:
            raise RecsError(
                'Output channel count must match the selected recorded channel count'
            )
        self.finished = finished
        self.failed = failed
        self.block_frames = block_frames
        self.position = 0
        self.paused = False
        self.stopped = False
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name='SessionPlayback')
        self._thread.start()

    def stop(self) -> None:
        with self._condition:
            self.stopped = True
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join()

    def pause(self) -> None:
        with self._condition:
            self.paused = True

    def resume(self) -> None:
        with self._condition:
            self.paused = False
            self._condition.notify_all()

    def jump(self, seconds: float) -> None:
        with self._condition:
            self.position = min(
                self.timeline.end,
                max(0, self.position + round(seconds * self.timeline.rate)),
            )

    @property
    def seconds(self) -> float:
        with self._condition:
            return self.position / self.timeline.rate

    def _run(self) -> None:
        import sounddevice

        try:
            channels = max(self.output_channels)
            stream = sounddevice.OutputStream(
                channels=channels,
                dtype='float32',
                samplerate=self.timeline.rate,
            )
        except (
            OSError,
            RecsError,
            soundfile.SoundFileError,
            sounddevice.PortAudioError,
        ) as error:
            self.failed(str(error))
            return
        playback_failed = False
        try:
            stream.start()
            while True:
                with self._condition:
                    while self.paused and not self.stopped:
                        self._condition.wait()
                    if self.stopped or self.position >= self.timeline.end:
                        break
                    start = self.position
                    frames = min(self.block_frames, self.timeline.end - start)
                    self.position += frames
                block = np.zeros((frames, channels), dtype=np.float32)
                block[
                    :, [channel - 1 for channel in self.output_channels]
                ] = self.timeline.read(start, frames)
                stream.write(block)
        except (
            OSError,
            RecsError,
            soundfile.SoundFileError,
            sounddevice.PortAudioError,
        ) as error:
            playback_failed = True
            self.failed(str(error))
        finally:
            stream.close()
            with self._condition:
                natural_end = (
                    not playback_failed
                    and not self.stopped
                    and self.position >= self.timeline.end
                )
            if natural_end:
                self.finished()


def select_stream(
    score: RecordingScore, source: str | None, channel: str | None
) -> AudioStream:
    streams = [
        stream for stream in score.body.streams if isinstance(stream, AudioStream)
    ]
    if source is not None:
        streams = [
            stream
            for stream in streams
            if source in {stream.source_id, stream.source_name}
        ]
        if not streams:
            raise RecsError(f'No recorded audio source: {source}')
    if channel is not None:
        streams = [stream for stream in streams if _channel_name(stream) == channel]
        if not streams:
            raise RecsError(f'No recorded channel or pair: {channel}')
    if not streams:
        raise RecsError('Selected session has no recorded audio')
    if source is None:
        source_name = max(
            {stream.source_name or stream.source_id for stream in streams},
            key=lambda name: max(
                _highest_channel(stream)
                for stream in streams
                if (stream.source_name or stream.source_id) == name
            ),
        )
        streams = [
            stream
            for stream in streams
            if (stream.source_name or stream.source_id) == source_name
        ]
    selected = max(
        streams, key=lambda stream: (_is_stereo(stream), _highest_channel(stream))
    )
    if len(selected.stream.channels) not in {1, 2}:
        raise RecsError(
            'Selected recorded stream must be one channel or an adjacent pair'
        )
    return selected


def parse_channels(value: str, label: str) -> tuple[int, ...]:
    try:
        channels = tuple(int(i) for i in value.split('-'))
    except ValueError as error:
        raise RecsError(
            f'{label} must be a channel or adjacent pair: {value}'
        ) from error
    if len(channels) not in {1, 2} or channels[0] < 1:
        raise RecsError(f'{label} must be a positive channel or adjacent pair: {value}')
    if len(channels) == 2 and channels[1] != channels[0] + 1:
        raise RecsError(f'{label} must be an adjacent pair: {value}')
    return channels


def default_output_channels(channels: int) -> tuple[int, ...]:
    """Choose the highest mono channel or adjacent stereo pair on default output."""
    import sounddevice

    outputs = int(sounddevice.query_devices(kind='output')['max_output_channels'])
    if outputs < channels:
        raise RecsError(
            f'Default output device has {outputs} channels; playback needs {channels}'
        )
    if channels == 2:
        return outputs - 1, outputs
    return (outputs,)


def _rate(score: RecordingScore, stream: AudioStream) -> int:
    for timebase in score.timebases:
        if timebase.name == stream.stream.timebase:
            if timebase.rate.denominator != 1:
                raise RecsError(
                    f'Audio timebase has a fractional rate: {timebase.name}'
                )
            return timebase.rate.numerator
    raise RecsError(f'Audio stream has no timebase: {stream.name}')


def _fragments(stream: AudioStream) -> list[AudioFragment]:
    selected: dict[str, AudioFragment] = {}
    for fragment in sorted(stream.fragments, key=lambda f: (f.start, f.asset)):
        key = fragment.variant_group or fragment.asset
        selected.setdefault(key, fragment)
    return sorted(selected.values(), key=lambda f: f.start)


def _channel_name(stream: AudioStream) -> str:
    return stream.track_name or '-'.join(
        str(_channel_number(channel)) for channel in stream.stream.channels
    )


def _highest_channel(stream: AudioStream) -> int:
    return max(_channel_number(channel) for channel in stream.stream.channels)


def _channel_number(channel: str) -> int:
    try:
        return int(channel.rsplit('-', 1)[-1])
    except ValueError as error:
        raise RecsError(
            f'Recorded channel has no numeric identity: {channel}'
        ) from error


def _is_stereo(stream: AudioStream) -> bool:
    return len(stream.stream.channels) == 2
