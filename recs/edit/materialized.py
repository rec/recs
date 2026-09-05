from pathlib import Path

import numpy as np
import soundfile

from recs.base.errors import RecsError
from recs.edit.graph import FrameRange
from recs.edit.record import ResolvedSource


class MaterializedAudio:
    def __init__(
        self,
        samples: np.ndarray,
        sample_rate: int,
        start_frame: int,
        observed_ranges: list[FrameRange],
    ) -> None:
        if samples.dtype != np.float32 or samples.ndim != 2:
            raise ValueError(
                'Materialized audio must be a two-dimensional float32 array'
            )
        if sample_rate <= 0 or start_frame < 0:
            raise ValueError('Invalid materialized audio timebase')
        end_frame = start_frame + len(samples)
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
        self.samples = samples
        self.sample_rate = sample_rate
        self.start_frame = start_frame
        self.observed_ranges = observed_ranges

    @property
    def end_frame(self) -> int:
        return self.start_frame + len(self.samples)

    @property
    def channels(self) -> int:
        return self.samples.shape[1]

    @property
    def nbytes(self) -> int:
        return self.samples.nbytes


def materialize_source(source: ResolvedSource) -> MaterializedAudio:
    samples = np.zeros((source.timeline_end, source.channels), dtype=np.float32)
    for fragment in source.fragments:
        _read_fragment(
            source,
            fragment.path,
            fragment.start,
            fragment.end,
            fragment.channel_offset,
            samples,
        )
    ranges = merge_ranges(
        [FrameRange(start=f.start, end=f.end) for f in source.fragments]
    )
    samples.flags.writeable = False
    return MaterializedAudio(samples, source.sample_rate, 0, ranges)


def select_audio(value: MaterializedAudio, start: int, end: int) -> MaterializedAudio:
    if not value.start_frame <= start < end <= value.end_frame:
        raise ValueError(f'Invalid materialized audio range {start}:{end}')
    ranges = [
        FrameRange(start=max(start, r.start), end=min(end, r.end))
        for r in value.observed_ranges
        if max(start, r.start) < min(end, r.end)
    ]
    return MaterializedAudio(
        value.samples[start - value.start_frame : end - value.start_frame],
        value.sample_rate,
        start,
        ranges,
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


def _read_fragment(
    source: ResolvedSource,
    path: Path,
    start: int,
    end: int,
    channel_offset: int,
    destination: np.ndarray,
) -> None:
    try:
        with soundfile.SoundFile(path) as fp:
            frames = end - start
            if channel_offset == 0 and fp.channels == source.channels:
                data = fp.read(
                    frames,
                    dtype='float32',
                    always_2d=True,
                    out=destination[start:end],
                )
                count = len(data)
            else:
                data = fp.read(frames, dtype='float32', always_2d=True)
                count = len(data)
                destination[start : start + count] = data[
                    :, channel_offset : channel_offset + source.channels
                ]
    except soundfile.SoundFileError as e:
        raise RecsError(f'Cannot read source audio {path}: {e}') from e
    if count != end - start:
        raise RecsError(
            f'Source audio {path} contains {count} frames; expected {end - start}'
        )
