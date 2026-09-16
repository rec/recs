"""Bounded, read-only measurements of one audio fragment."""

from math import sqrt
from pathlib import Path

import numpy as np
import soundfile
from pydantic import BaseModel, Field

from ..base.errors import RecsError


class AnalysisSettings(BaseModel, frozen=True):
    """Limits apply independently to each fragment and its channels."""

    near_full_scale_dbfs: float = Field(default=-0.1, le=0, allow_inf_nan=False)
    """Advisory threshold for absolute sample amplitude, in dBFS."""
    max_seconds: float = Field(default=60, gt=0, allow_inf_nan=False)
    """Analyze at most this prefix of each fragment, in seconds."""
    max_runs: int = Field(default=100, ge=1)
    """Retain at most this many run ranges per channel; count omitted runs."""


class NearFullScaleRun(BaseModel, frozen=True):
    asset_start_frame: int
    asset_end_frame: int
    source_start_frame: int | None
    source_end_frame: int | None


class ChannelMeasurement(BaseModel, frozen=True):
    channel: str
    peak: float
    rms: float
    near_full_scale_frames: int
    runs: list[NearFullScaleRun]
    omitted_runs: int


class AudioMeasurement(BaseModel, frozen=True):
    asset: str
    asset_start_frame: int
    source_start_frame: int | None
    analyzed_frames: int
    unexamined_frames: int
    channels: list[ChannelMeasurement]


def measure(
    path: Path,
    asset: str,
    asset_start: int,
    source_start: int | None,
    count: int,
    channels: list[str],
    sample_rate: float,
    settings: AnalysisSettings,
) -> AudioMeasurement:
    """Measure a prefix; run endpoints are half-open and never cross fragments."""
    threshold = 10 ** (settings.near_full_scale_dbfs / 20)
    width = len(channels)
    peaks = np.zeros(width)
    squares = np.zeros(width)
    near = np.zeros(width, dtype=np.int64)
    starts: list[int | None] = [None] * width
    runs: list[list[NearFullScaleRun]] = [[] for _ in channels]
    omitted = [0] * width

    def finish(channel: int, end: int) -> None:
        start = starts[channel]
        if start is None:
            return
        if len(runs[channel]) < settings.max_runs:
            runs[channel].append(
                NearFullScaleRun(
                    asset_start_frame=asset_start + start,
                    asset_end_frame=asset_start + end,
                    source_start_frame=None
                    if source_start is None
                    else source_start + start,
                    source_end_frame=None
                    if source_start is None
                    else source_start + end,
                )
            )
        else:
            omitted[channel] += 1
        starts[channel] = None

    analyzed = 0
    with soundfile.SoundFile(path) as audio:
        if audio.channels != width or audio.samplerate != sample_rate:
            raise RecsError('Audio layout or rate disagrees with the recording')
        if asset_start + count > audio.frames:
            raise RecsError('Fragment exceeds decoded audio extent')
        audio.seek(asset_start)
        limit = (
            count
            if settings.max_seconds >= count / sample_rate
            else int(settings.max_seconds * sample_rate)
        )
        while analyzed < limit:
            block = audio.read(
                min(48_000, limit - analyzed), dtype='float64', always_2d=True
            )
            if not len(block):
                raise RecsError('Audio payload ended before the requested range')
            if not np.isfinite(block).all():
                raise RecsError(
                    'Audio contains non-finite samples in the analyzed range'
                )
            magnitude = np.abs(block)
            peaks = np.maximum(peaks, magnitude.max(axis=0))
            squares += np.square(block).sum(axis=0)
            mask = magnitude >= threshold
            near += mask.sum(axis=0)
            for channel in range(width):
                active = mask[:, channel]
                boundaries = np.flatnonzero(np.diff(active.astype(np.int8))) + 1
                if active[0] and starts[channel] is None:
                    starts[channel] = analyzed
                elif not active[0]:
                    finish(channel, analyzed)
                for boundary in boundaries:
                    position = analyzed + int(boundary)
                    if active[boundary]:
                        starts[channel] = position
                    else:
                        finish(channel, position)
            analyzed += len(block)
    for channel in range(width):
        finish(channel, analyzed)
    return AudioMeasurement(
        asset=asset,
        asset_start_frame=asset_start,
        source_start_frame=source_start,
        analyzed_frames=analyzed,
        unexamined_frames=count - analyzed,
        channels=[
            ChannelMeasurement(
                channel=c,
                peak=float(peaks[i]),
                rms=sqrt(float(squares[i]) / analyzed) if analyzed else 0,
                near_full_scale_frames=int(near[i]),
                runs=runs[i],
                omitted_runs=omitted[i],
            )
            for i, c in enumerate(channels)
        ],
    )
