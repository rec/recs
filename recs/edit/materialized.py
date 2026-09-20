from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryFile, gettempdir

import numpy as np
import soundfile
from pydantic import BaseModel, ConfigDict
from ufor.assets import Asset, ContentIdentity, RelativeFileLocation
from ufor.recording import RecordingScore

from recs.base.errors import RecsError
from recs.edit.graph import FrameRange
from recs.edit.record import ResolvedSource
from recs.edit.workspace import SCRATCH_DIRECTORY, check_space

BLOCK_FRAMES = 65_536


class AudioStorage:
    """Unencoded float32 scratch storage, released with its last audio view."""

    def __init__(self, frames: int, channels: int) -> None:
        self.frames = frames
        self.channels = channels
        try:
            directory = SCRATCH_DIRECTORY.get() or Path(gettempdir())
            check_space(frames * channels * 4, directory, 0)
            self.file = TemporaryFile(dir=directory)
        except OSError as error:
            raise RecsError(
                f'Cannot create temporary audio storage: {error}'
            ) from error
        self.peak_buffer_bytes = BLOCK_FRAMES * channels * 8
        try:
            self.file.truncate(frames * channels * 4)
        except OSError as error:
            self.file.close()
            raise RecsError(
                f'Cannot allocate temporary audio storage: {error}'
            ) from error

    def read(self, start: int, frames: int) -> np.ndarray:
        try:
            self.file.seek(start * self.channels * 4)
            data = self.file.read(frames * self.channels * 4)
        except OSError as error:
            raise RecsError(f'Cannot read temporary audio storage: {error}') from error
        if len(data) != frames * self.channels * 4:
            raise RecsError('Temporary audio storage is truncated')
        return np.frombuffer(data, dtype='<f4').reshape(frames, self.channels)

    def write(self, start: int, samples: np.ndarray) -> None:
        try:
            self.file.seek(start * self.channels * 4)
            self.file.write(samples.astype('<f4', copy=False).tobytes())
        except OSError as error:
            raise RecsError(f'Cannot write temporary audio storage: {error}') from error


class MaterializedAudio:
    def __init__(
        self,
        storage: AudioStorage,
        sample_rate: int,
        start_frame: int,
        observed_ranges: list[FrameRange],
        *,
        storage_start: int = 0,
        frames: int | None = None,
        channel_start: int = 0,
        channels: int | None = None,
    ) -> None:
        frames = storage.frames - storage_start if frames is None else frames
        channels = storage.channels - channel_start if channels is None else channels
        if sample_rate <= 0 or start_frame < 0:
            raise ValueError('Invalid materialized audio timebase')
        end_frame = start_frame + frames
        if any(
            r.start < start_frame or r.end > end_frame or r.end <= r.start
            for r in observed_ranges
        ):
            raise ValueError('Observed range is outside materialized audio')
        if any(
            a.end > b.start
            for a, b in zip(observed_ranges, observed_ranges[1:], strict=False)
        ):
            raise ValueError('Observed ranges overlap')
        self.storage = storage
        self.storage_start = storage_start
        self.channel_start = channel_start
        self.sample_rate = sample_rate
        self.start_frame = start_frame
        self.end_frame = end_frame
        self.channels = channels
        self.observed_ranges = observed_ranges

    def read(self, start: int, frames: int) -> np.ndarray:
        if not 0 <= frames <= BLOCK_FRAMES:
            raise ValueError(f'Audio reads must contain at most {BLOCK_FRAMES} frames')
        if start < self.start_frame or start + frames > self.end_frame:
            raise ValueError('Audio read is outside the prepared range')
        data = self.storage.read(self.storage_start + start - self.start_frame, frames)
        return data[:, self.channel_start : self.channel_start + self.channels]

    def blocks(
        self, start: int | None = None, end: int | None = None
    ) -> Iterator[np.ndarray]:
        start = self.start_frame if start is None else start
        end = self.end_frame if end is None else end
        for position in range(start, end, BLOCK_FRAMES):
            yield self.read(position, min(BLOCK_FRAMES, end - position))

    @property
    def nbytes(self) -> int:
        return (self.end_frame - self.start_frame) * self.channels * 4

    @property
    def timeline_end(self) -> int:
        return self.end_frame


class MaterializedTrack(BaseModel, frozen=True):
    source: str
    track_name: str
    stream_id: str
    audio: MaterializedAudio

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)


class MaterializedSession(BaseModel, frozen=True):
    session_id: str
    duration_frames: int
    tracks: list[MaterializedTrack]

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)


class SourceMaterializer:
    def __init__(self) -> None:
        self.audio: dict[str, MaterializedAudio] = {}

    def materialize(self, source: ResolvedSource) -> MaterializedAudio:
        key = source.model_dump_json(exclude={'name'})
        if key not in self.audio:
            self.audio[key] = materialize_source(source)
        return self.audio[key]


def estimate_audio_buffers(widths: dict[str, int], source_width: int) -> int:
    width = max(widths.values(), default=1)
    return BLOCK_FRAMES * 4 * (sum(widths.values()) + source_width + 4 * width + 32)


def allocate_audio(frames: int, channels: int, purpose: str) -> np.ndarray:
    size = frames * channels * np.dtype(np.float32).itemsize
    try:
        return np.zeros((frames, channels), dtype=np.float32)
    except MemoryError as e:
        raise RecsError(
            f'Cannot allocate {size} bytes for materialized audio: {purpose}'
        ) from e


def materialize_source(source: ResolvedSource) -> MaterializedAudio:
    storage = AudioStorage(source.timeline_end, source.channels)
    for fragment in source.fragments:
        try:
            with soundfile.SoundFile(fragment.path) as fp:
                storage.peak_buffer_bytes = max(
                    storage.peak_buffer_bytes,
                    BLOCK_FRAMES * (fp.channels + source.channels) * 4,
                )
                fp.seek(fragment.asset_start)
                for start in range(fragment.start, fragment.end, BLOCK_FRAMES):
                    count = min(BLOCK_FRAMES, fragment.end - start)
                    data = fp.read(count, dtype='float32', always_2d=True)
                    if len(data) != count:
                        raise RecsError(f'Source audio {fragment.path} is truncated')
                    storage.write(
                        start,
                        data[
                            :,
                            fragment.channel_offset : fragment.channel_offset
                            + source.channels,
                        ],
                    )
        except soundfile.SoundFileError as error:
            raise RecsError(
                f'Cannot read source audio {fragment.path}: {error}'
            ) from error
    ranges = merge_ranges(
        [FrameRange(start=f.start, end=f.end) for f in source.fragments]
    )
    return MaterializedAudio(storage, source.sample_rate, 0, ranges)


def select_audio(value: MaterializedAudio, start: int, end: int) -> MaterializedAudio:
    if not value.start_frame <= start < end <= value.end_frame:
        raise ValueError(f'Invalid materialized audio range {start}:{end}')
    ranges = [
        FrameRange(start=max(start, r.start), end=min(end, r.end))
        for r in value.observed_ranges
        if max(start, r.start) < min(end, r.end)
    ]
    return MaterializedAudio(
        value.storage,
        value.sample_rate,
        start,
        ranges,
        storage_start=value.storage_start + start - value.start_frame,
        frames=end - start,
        channel_start=value.channel_start,
        channels=value.channels,
    )


def select_channels(value: MaterializedAudio, channels: list[int]) -> MaterializedAudio:
    if not channels or channels != list(range(channels[0], channels[-1] + 1)):
        raise ValueError('Materialized channels must be consecutive')
    if channels[0] < 0 or channels[-1] >= value.channels:
        raise ValueError(
            f'Channel selection exceeds width {value.channels}: {channels}'
        )
    return MaterializedAudio(
        value.storage,
        value.sample_rate,
        value.start_frame,
        value.observed_ranges,
        storage_start=value.storage_start,
        frames=value.end_frame - value.start_frame,
        channel_start=value.channel_start + channels[0],
        channels=len(channels),
    )


def merge_ranges(values: list[FrameRange]) -> list[FrameRange]:
    result: list[FrameRange] = []
    for value in sorted(values, key=lambda r: (r.start, r.end)):
        if result and value.start <= result[-1].end:
            result[-1] = FrameRange(
                start=result[-1].start, end=max(result[-1].end, value.end)
            )
        else:
            result.append(value)
    return result


def recording_definition(
    value: MaterializedAudio, name: str, channels: list[str]
) -> RecordingScore:
    """Describe a prepared audio value for the host's score/asset provider."""
    from hashlib import sha256

    from ufor.interface import Output, StreamBinding
    from ufor.recording import (
        AudioFragment,
        AudioStream,
        Gap,
        GapReason,
        Recording,
    )
    from ufor.streams import AudioType
    from ufor.time import Rate, Timebase

    clock = Timebase(name='audio', rate=Rate(numerator=value.sample_rate))
    stream = AudioType(timebase='audio', channels=channels)
    fragments = [
        AudioFragment(
            asset='samples',
            start=r.start,
            count=r.end - r.start,
            asset_start=r.start - value.start_frame,
        )
        for r in value.observed_ranges
    ]
    gaps = []
    end = 0
    for span in value.observed_ranges:
        if span.start > end:
            gaps.append(Gap(start=end, end=span.start, reason=GapReason.unknown))
        end = span.end
    if end < value.end_frame:
        gaps.append(Gap(start=end, end=value.end_frame, reason=GapReason.unknown))
    digest = sha256()
    for block in value.blocks():
        digest.update(block.astype('<f4', copy=False).tobytes())
    asset = Asset(
        name='samples',
        location=RelativeFileLocation(path='samples.f32'),
        encoding='float32le',
        content=ContentIdentity(
            byte_length=value.nbytes,
            sha256=digest.hexdigest(),
        ),
    )
    return RecordingScore(
        name=name,
        title=name,
        timebases=[clock],
        assets=[asset],
        outputs=[
            Output(name='audio', stream=stream, binding=StreamBinding(stream='audio'))
        ],
        body=Recording(
            state='sealed',
            streams=[
                AudioStream(
                    name='audio',
                    source_id=name,
                    stream=stream,
                    end=value.end_frame,
                    fragments=fragments,
                    gaps=gaps,
                )
            ],
        ),
    )
