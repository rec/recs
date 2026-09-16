import math
from collections.abc import Callable, Iterable, Iterator

import numpy as np
from pydantic import BaseModel, ConfigDict

from recs.base.errors import RecsError
from recs.edit.calibration_schema import (
    CalibratedThreshold,
    CalibrationSettings,
    FrameRange,
    LevelWindow,
    SilenceSettings,
)
from recs.edit.materialized import MaterializedAudio, SourceMaterializer
from recs.edit.record import ResolvedSource

HISTOGRAM_BIN_DB = 0.1


def level_windows(
    source: ResolvedSource, settings: CalibrationSettings
) -> Iterator[LevelWindow]:
    yield from level_windows_audio(SourceMaterializer().materialize(source), settings)


def level_windows_audio(
    source: MaterializedAudio, settings: CalibrationSettings
) -> Iterator[LevelWindow]:
    for coverage in source.observed_ranges:
        start = _aligned_start(coverage.start, settings.window_frames)
        while start + settings.window_frames <= coverage.end:
            end = start + settings.window_frames
            minima = np.full(source.channels, np.inf, dtype=np.float32)
            maxima = np.full(source.channels, -np.inf, dtype=np.float32)
            for block in source.blocks(start, end):
                minima = np.minimum(minima, np.min(block, axis=0))
                maxima = np.maximum(maxima, np.max(block, axis=0))
            yield LevelWindow(
                start=start,
                end=end,
                level_dbfs=_level_dbfs(
                    np.stack((minima, maxima)), settings.analysis_floor_dbfs
                ),
                coverage_start=coverage.start,
                coverage_end=coverage.end,
            )
            start = end


def calibrate_threshold(
    source: str,
    windows: Callable[[], Iterable[LevelWindow]],
    settings: CalibrationSettings,
) -> CalibratedThreshold:
    all_levels = _Histogram(settings.analysis_floor_dbfs)
    for window in windows():
        all_levels.add(window.level_dbfs)
    if not all_levels.count:
        raise RecsError(f'{source}: no complete observed analysis window')

    provisional = all_levels.percentile(settings.candidate_percentile)
    ceiling = provisional + settings.candidate_tolerance_db
    result, closest = _first_silence(windows(), ceiling, settings)
    if result is None:
        raise RecsError(
            f'{source}: no sustained silence; provisional quiet level '
            f'{provisional:.1f} dBFS, required {settings.minimum_silence_frames} '
            f'frames, closest candidate {closest} frames'
        )
    start, end, levels = result
    measured_dbfs = levels.percentile(settings.noise_percentile)
    threshold_dbfs = min(0.0, measured_dbfs + settings.signal_margin_db)
    return CalibratedThreshold(
        source=source,
        silence_start=start,
        silence_end=end,
        provisional_quiet_level_dbfs=round(provisional, 1),
        measured_noise_floor=round(-measured_dbfs, 1),
        noise_floor=round(-threshold_dbfs, 1),
        observed_window_count=all_levels.count,
        window_count=levels.count,
    )


def detect_intervals(
    windows: Iterable[LevelWindow],
    threshold: CalibratedThreshold,
    settings: SilenceSettings,
) -> list[FrameRange]:
    active = _active_ranges(windows, -threshold.noise_floor)
    joined = _join_nearby(active, settings.stop_after_quiet_frames)
    padded = [
        _ObservedRange(
            start=max(r.coverage_start, r.start - settings.quiet_before_frames),
            end=min(r.coverage_end, r.end + settings.quiet_after_frames),
            coverage_start=r.coverage_start,
            coverage_end=r.coverage_end,
        )
        for r in joined
    ]
    merged = _join_overlapping(padded)
    result: list[FrameRange] = []
    for item in merged:
        if item.end - item.start < settings.shortest_file_frames:
            continue
        if not settings.longest_file_frames:
            result.append(FrameRange(start=item.start, end=item.end))
            continue
        for start in range(item.start, item.end, settings.longest_file_frames):
            result.append(
                FrameRange(
                    start=start,
                    end=min(start + settings.longest_file_frames, item.end),
                )
            )
    return result


class _ObservedRange(BaseModel, frozen=True):
    start: int
    end: int
    coverage_start: int
    coverage_end: int

    model_config = ConfigDict(extra='forbid')


class _Histogram:
    def __init__(self, floor: float) -> None:
        self.floor = floor
        self.bins = [0] * (math.ceil(-floor / HISTOGRAM_BIN_DB) + 1)
        self.count = 0

    def add(self, value: float) -> None:
        value = min(0.0, max(self.floor, value))
        index = min(len(self.bins) - 1, int((value - self.floor) / HISTOGRAM_BIN_DB))
        self.bins[index] += 1
        self.count += 1

    def percentile(self, percentile: float) -> float:
        if not self.count:
            raise ValueError('Cannot find percentile of empty histogram')
        target = max(1, math.ceil(self.count * percentile / 100))
        cumulative = 0
        for index, count in enumerate(self.bins):
            cumulative += count
            if cumulative >= target:
                return self.floor + index * HISTOGRAM_BIN_DB
        return 0.0


def _aligned_start(start: int, window_frames: int) -> int:
    return math.ceil(start / window_frames) * window_frames


def _level_dbfs(block: np.ndarray, floor: float) -> float:
    amplitudes = (np.max(block, axis=0) - np.min(block, axis=0)) / 2
    amplitude = float(np.mean(amplitudes))
    if amplitude <= 0:
        return floor
    return max(floor, 20 * math.log10(amplitude))


def _first_silence(
    windows: Iterable[LevelWindow],
    ceiling: float,
    settings: CalibrationSettings,
) -> tuple[tuple[int, int, _Histogram] | None, int]:
    start: int | None = None
    end = 0
    coverage_end = 0
    levels = _Histogram(settings.analysis_floor_dbfs)
    qualified = False
    closest = 0
    for window in windows:
        contiguous = start is not None and end == window.start
        quiet = window.level_dbfs <= ceiling
        if not quiet or (start is not None and not contiguous):
            if start is not None:
                duration = end - start
                closest = max(closest, duration)
                if qualified:
                    return (start, end, levels), closest
            start = None
            levels = _Histogram(settings.analysis_floor_dbfs)
            qualified = False
        if not quiet:
            continue
        if start is None:
            start = window.start
            coverage_end = window.coverage_end
        elif window.coverage_end != coverage_end:
            raise RecsError('Silence candidate crossed an unobserved source gap')
        end = window.end
        levels.add(window.level_dbfs)
        qualified = end - start >= settings.minimum_silence_frames
    if start is not None:
        closest = max(closest, end - start)
        if qualified:
            return (start, end, levels), closest
    return None, closest


def _active_ranges(
    windows: Iterable[LevelWindow], threshold_dbfs: float
) -> list[_ObservedRange]:
    result: list[_ObservedRange] = []
    current: _ObservedRange | None = None
    for window in windows:
        if window.level_dbfs < threshold_dbfs:
            if current is not None:
                result.append(current)
                current = None
            continue
        if (
            current is not None
            and current.end == window.start
            and current.coverage_end == window.coverage_end
        ):
            current = current.model_copy(update={'end': window.end})
        else:
            if current is not None:
                result.append(current)
            current = _ObservedRange(
                start=window.start,
                end=window.end,
                coverage_start=window.coverage_start,
                coverage_end=window.coverage_end,
            )
    if current is not None:
        result.append(current)
    return result


def _join_nearby(
    values: list[_ObservedRange], maximum_gap: int
) -> list[_ObservedRange]:
    result: list[_ObservedRange] = []
    for value in values:
        if (
            result
            and result[-1].coverage_end == value.coverage_end
            and value.start - result[-1].end <= maximum_gap
        ):
            result[-1] = result[-1].model_copy(update={'end': value.end})
        else:
            result.append(value)
    return result


def _join_overlapping(values: list[_ObservedRange]) -> list[_ObservedRange]:
    result: list[_ObservedRange] = []
    for value in values:
        if (
            result
            and result[-1].coverage_end == value.coverage_end
            and value.start <= result[-1].end
        ):
            result[-1] = result[-1].model_copy(
                update={'end': max(result[-1].end, value.end)}
            )
        else:
            result.append(value)
    return result
