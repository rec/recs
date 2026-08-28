from typing import NamedTuple

import numpy as np

from recs.base.waveform import (
    WaveformBatchData,
    WaveformLayoutData,
    WaveformTrackData,
    WaveformTrackLayout,
)

from .block import Block


class LiveWaveform:
    def __init__(
        self,
        source: str,
        sample_rate: int,
        tracks: list[WaveformTrackLayout],
        generation: int,
        bucket_milliseconds: int,
        batch_milliseconds: int,
    ) -> None:
        self.source = source
        self.sample_rate = sample_rate
        self.tracks = tracks
        self.generation = generation
        self.bucket_frames = max(1, round(sample_rate * bucket_milliseconds / 1_000))
        self.batch_buckets = batch_milliseconds // bucket_milliseconds
        self.sequence = 0
        self.expected_frame: int | None = None
        self.bucket_start: int | None = None
        self.bucket_timestamp = 0.0
        self.bucket_frame_count = 0
        self.minimum: list[np.ndarray] = []
        self.maximum: list[np.ndarray] = []
        self.pending: list[_Bucket] = []

    @property
    def layout(self) -> WaveformLayoutData:
        return WaveformLayoutData(
            source=self.source,
            generation=self.generation,
            sample_rate=self.sample_rate,
            bucket_frames=self.bucket_frames,
            tracks=self.tracks,
        )

    def receive(
        self,
        blocks: list[Block],
        start_frame: int,
        start_timestamp: float,
    ) -> list[WaveformBatchData]:
        self._validate_blocks(blocks)
        result: list[WaveformBatchData] = []
        if self.expected_frame is not None and start_frame != self.expected_frame:
            self._record_discontinuity(result)

        frame_count = len(blocks[0])
        self.expected_frame = start_frame + frame_count
        frame = start_frame
        offset = 0
        while offset < frame_count:
            if self.bucket_start is None:
                aligned = _aligned_frame(frame, self.bucket_frames)
                skipped = min(frame_count - offset, aligned - frame)
                frame += skipped
                offset += skipped
                if offset == frame_count:
                    break
                self._start_bucket(
                    frame,
                    start_timestamp + offset / self.sample_rate,
                    blocks,
                )

            assert self.bucket_start is not None
            available = self.bucket_start + self.bucket_frames - frame
            consumed = min(frame_count - offset, available)
            self._reduce(blocks, slice(offset, offset + consumed))
            self.bucket_frame_count += consumed
            frame += consumed
            offset += consumed
            if self.bucket_frame_count == self.bucket_frames:
                self._finish_bucket(True, result)

        return result

    def _validate_blocks(self, blocks: list[Block]) -> None:
        if len(blocks) != len(self.tracks):
            raise ValueError('Waveform block count does not match track count')
        if not blocks:
            raise ValueError('Waveform requires at least one track')
        frame_counts = {len(b) for b in blocks}
        if len(frame_counts) != 1:
            raise ValueError('Waveform blocks have different frame counts')
        for block, track in zip(blocks, self.tracks, strict=True):
            if block.channel_count != len(track.channels):
                raise ValueError('Waveform block channel count does not match track')

    def _start_bucket(
        self,
        frame: int,
        timestamp: float,
        blocks: list[Block],
    ) -> None:
        self.bucket_start = frame
        self.bucket_timestamp = timestamp
        self.bucket_frame_count = 0
        self.minimum = [np.full(b.channel_count, np.inf) for b in blocks]
        self.maximum = [np.full(b.channel_count, -np.inf) for b in blocks]

    def _reduce(self, blocks: list[Block], frames: slice) -> None:
        for i, block in enumerate(blocks):
            values = block.block[frames]
            minimum = values.min(axis=0) / block.scale
            maximum = values.max(axis=0) / block.scale
            if not np.isfinite(minimum).all() or not np.isfinite(maximum).all():
                raise ValueError('Waveform input contains non-finite samples')
            self.minimum[i] = np.minimum(self.minimum[i], minimum)
            self.maximum[i] = np.maximum(self.maximum[i], maximum)

    def _record_discontinuity(self, result: list[WaveformBatchData]) -> None:
        if self.bucket_start is not None:
            self._finish_bucket(False, result)
        self._flush(result)

    def _finish_bucket(self, present: bool, result: list[WaveformBatchData]) -> None:
        assert self.bucket_start is not None
        minimum = (
            [v.tolist() for v in self.minimum]
            if present
            else [[0.0] * len(t.channels) for t in self.tracks]
        )
        maximum = (
            [v.tolist() for v in self.maximum]
            if present
            else [[0.0] * len(t.channels) for t in self.tracks]
        )
        self.pending.append(
            _Bucket(
                start_frame=self.bucket_start,
                start_timestamp=self.bucket_timestamp,
                present=present,
                minimum=minimum,
                maximum=maximum,
            )
        )
        self.bucket_start = None
        self.bucket_frame_count = 0
        self.minimum = []
        self.maximum = []
        if len(self.pending) == self.batch_buckets:
            self._flush(result)

    def _flush(self, result: list[WaveformBatchData]) -> None:
        if not self.pending:
            return
        tracks = [
            WaveformTrackData(
                channels=track.channels,
                minimum=[
                    [b.minimum[i][c] for b in self.pending]
                    for c in range(len(track.channels))
                ],
                maximum=[
                    [b.maximum[i][c] for b in self.pending]
                    for c in range(len(track.channels))
                ],
            )
            for i, track in enumerate(self.tracks)
        ]
        first = self.pending[0]
        result.append(
            WaveformBatchData(
                source=self.source,
                generation=self.generation,
                sequence=self.sequence,
                sample_rate=self.sample_rate,
                bucket_frames=self.bucket_frames,
                start_frame=first.start_frame,
                start_timestamp=first.start_timestamp,
                present=[b.present for b in self.pending],
                tracks=tracks,
            )
        )
        self.sequence += 1
        self.pending = []


class _Bucket(NamedTuple):
    start_frame: int
    start_timestamp: float
    present: bool
    minimum: list[list[float]]
    maximum: list[list[float]]


def _aligned_frame(frame: int, bucket_frames: int) -> int:
    return ((frame + bucket_frames - 1) // bucket_frames) * bucket_frames
