import math
import os
import re
import uuid
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import soundfile
import tomlkit
import tyro
from pydantic import BaseModel, ConfigDict, Field, model_validator
from reccy.configuration import units
from reccy.configuration.tyro import unit_spec
from typing_extensions import Self

from recs.base.errors import RecsError
from recs.base.types import Format, Subtype
from recs.edit.graph import FrameRange as ObservedFrameRange
from recs.edit.materialized import MaterializedAudio, SourceMaterializer
from recs.edit.output import bit_depth
from recs.edit.record import ResolvedSource, resolve_sources
from recs.edit.schema import EditSpec, SourceSpec
from recs.ui import session_record

HISTOGRAM_BIN_DB = 0.1
TIME_SPEC = unit_spec(units.Seconds, 'TIME')


class AutocalibrateOptions(BaseModel, frozen=True):
    """Infer noise from each track's first sustained silence and keep it fixed."""

    channel: Annotated[
        list[str], tyro.conf.arg(help='SOURCE:TRACK selector; repeat to select several')
    ] = Field(default_factory=list)

    window_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=0.1, gt=0)

    candidate_percentile: float = Field(default=20.0, ge=0, le=100)

    candidate_tolerance_db: float = Field(default=3.0, ge=0)

    minimum_silence_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=0.5, gt=0)

    noise_percentile: float = Field(default=95.0, ge=0, le=100)

    signal_margin_db: float = Field(default=6.0, ge=0)

    analysis_floor_dbfs: float = Field(default=-160.0, lt=0)

    quiet_before: Annotated[units.Seconds, TIME_SPEC] = Field(default=1.0, ge=0)

    quiet_after: Annotated[units.Seconds, TIME_SPEC] = Field(default=2.0, ge=0)

    stop_after_quiet: Annotated[units.Seconds, TIME_SPEC] = Field(default=20.0, ge=0)

    shortest_file_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=1.0, ge=0)

    longest_file_time: Annotated[units.Seconds, TIME_SPEC] = Field(default=0.0, ge=0)

    format: Format | None = None

    subtype: Subtype | None = None

    model_config = ConfigDict(extra='forbid')


class CalibrationSettings(BaseModel, frozen=True):
    window_frames: int = Field(default=4_800, gt=0)
    candidate_percentile: float = Field(default=20.0, ge=0, le=100)
    candidate_tolerance_db: float = Field(default=3.0, ge=0)
    minimum_silence_frames: int = Field(default=24_000, gt=0)
    noise_percentile: float = Field(default=95.0, ge=0, le=100)
    signal_margin_db: float = Field(default=6.0, ge=0)
    analysis_floor_dbfs: float = Field(default=-160.0, lt=0)

    model_config = ConfigDict(extra='forbid')


class SilenceSettings(BaseModel, frozen=True):
    quiet_before_frames: int = Field(default=48_000, ge=0)
    quiet_after_frames: int = Field(default=96_000, ge=0)
    stop_after_quiet_frames: int = Field(default=960_000, ge=0)
    shortest_file_frames: int = Field(default=48_000, ge=0)
    longest_file_frames: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra='forbid')


class AutocalibrateOutput(BaseModel, frozen=True):
    format: Format | None = Format.flac
    subtype: Subtype | None = Subtype.pcm_24

    model_config = ConfigDict(extra='forbid')


class CalibratedThreshold(BaseModel, frozen=True):
    source: str
    silence_start: int = Field(ge=0)
    silence_end: int = Field(gt=0)
    provisional_quiet_level_dbfs: float = Field(le=0)
    measured_noise_floor: float = Field(ge=0)
    noise_floor: float = Field(ge=0)
    observed_window_count: int = Field(gt=0)
    window_count: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_range(self) -> Self:
        if self.silence_end <= self.silence_start:
            raise ValueError('silence_end must be greater than silence_start')
        return self

    model_config = ConfigDict(extra='forbid')


class AutocalibrateEdit(BaseModel, frozen=True):
    schema_version: Literal[1] = 1
    kind: Literal['autocalibrate'] = 'autocalibrate'
    record: Path | None = None
    memory: str | None = None
    channels: list[str] = Field(default_factory=list)
    sample_rate: int | None = Field(default=None, gt=0)
    calibration: CalibrationSettings = CalibrationSettings()
    silence: SilenceSettings = SilenceSettings()
    output: AutocalibrateOutput = AutocalibrateOutput()
    thresholds: list[CalibratedThreshold] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_source(self) -> Self:
        if (self.record is None) == (self.memory is None):
            raise ValueError('autocalibration requires exactly one of record or memory')
        return self

    model_config = ConfigDict(extra='forbid')


class LevelWindow(BaseModel, frozen=True):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    level_dbfs: float
    coverage_start: int = Field(ge=0)
    coverage_end: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_ranges(self) -> Self:
        if self.end <= self.start:
            raise ValueError('window end must be greater than start')
        if not self.coverage_start <= self.start < self.end <= self.coverage_end:
            raise ValueError('window must remain inside observed coverage')
        return self

    model_config = ConfigDict(extra='forbid')


class FrameRange(BaseModel, frozen=True):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode='after')
    def validate_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError('range end must be greater than start')
        return self

    model_config = ConfigDict(extra='forbid')


class PreparedAutocalibrate(BaseModel, frozen=True):
    edit: AutocalibrateEdit
    sources: dict[str, ResolvedSource]
    audio: dict[str, MaterializedAudio]
    track_ids: dict[str, str]
    intervals: dict[str, list[FrameRange]]

    model_config = ConfigDict(extra='forbid', arbitrary_types_allowed=True)


def parse_autocalibrate(text: str) -> AutocalibrateEdit:
    return AutocalibrateEdit.model_validate(tomlkit.parse(text))


def canonical_autocalibrate(value: AutocalibrateEdit) -> str:
    return tomlkit.dumps(value.model_dump(mode='json', exclude_none=True))


def autocalibrate_from_options(
    record: Path, options: AutocalibrateOptions
) -> AutocalibrateEdit:
    record = record.resolve()
    _, _, sample_rate = _resolve_record_sources(record, options.channel)
    return _autocalibrate_from_options(
        record, None, options.channel, sample_rate, options
    )


def autocalibrate_from_materialized(
    memory: str,
    channels: list[str],
    sample_rate: int,
    options: AutocalibrateOptions,
) -> AutocalibrateEdit:
    return _autocalibrate_from_options(None, memory, channels, sample_rate, options)


def is_autocalibrate_file(path: Path) -> bool:
    if not path.is_file():
        return False
    return tomlkit.parse(path.read_text()).get('kind') == 'autocalibrate'


def prepare_autocalibrate(
    edit: AutocalibrateEdit, edit_directory: Path, destination: Path
) -> PreparedAutocalibrate:
    if destination.exists():
        raise RecsError(f'Output session directory already exists: {destination}')
    if edit.record is None:
        raise RecsError(
            'Autocalibration memory input is valid only inside a composition'
        )
    record_path = (edit_directory / edit.record).resolve()
    sources, track_ids, sample_rate = _resolve_record_sources(
        record_path, edit.channels
    )
    materializer = SourceMaterializer()
    audio = {k: materializer.materialize(v) for k, v in sources.items()}
    canonical = edit.model_copy(
        update={'record': _relative_path(record_path, destination)}
    )
    return _prepare_materialized(canonical, sources, audio, track_ids, sample_rate)


def prepare_materialized_autocalibrate(
    edit: AutocalibrateEdit,
    audio: dict[str, MaterializedAudio],
    track_ids: dict[str, str],
    destination: Path,
) -> PreparedAutocalibrate:
    if destination.exists():
        raise RecsError(f'Output session directory already exists: {destination}')
    sample_rates = {a.sample_rate for a in audio.values()}
    if len(sample_rates) != 1:
        raise RecsError(f'Selected tracks have mixed sample rates: {sample_rates}')
    return _prepare_materialized(edit, {}, audio, track_ids, next(iter(sample_rates)))


def autocalibrate_summary(prepared: PreparedAutocalibrate) -> str:
    if (sample_rate := prepared.edit.sample_rate) is None:
        raise RecsError('Prepared autocalibration has no sample rate')
    lines = [
        f'Record: {prepared.edit.record}',
        f'Sample rate: {sample_rate}',
        'Calibration: first sustained silence per track; fixed thereafter',
    ]
    thresholds = {t.source: t for t in prepared.edit.thresholds}
    for selector, intervals in prepared.intervals.items():
        threshold = thresholds[selector]
        frames = sum(r.end - r.start for r in intervals)
        file_word = 'file' if len(intervals) == 1 else 'files'
        lines.extend(
            [
                f'{selector}:',
                f'  Provisional quiet: '
                f'{threshold.provisional_quiet_level_dbfs:.1f} dBFS',
                f'  First silence: {threshold.silence_start}:{threshold.silence_end}',
                f'  Observed windows: {threshold.observed_window_count}',
                f'  Measured noise: {-threshold.measured_noise_floor:.1f} dBFS',
                f'  Threshold: {-threshold.noise_floor:.1f} dBFS '
                f'(noise_floor = {threshold.noise_floor:.1f})',
                f'  Output: {len(intervals)} {file_word}, {frames} frames '
                f'({frames / sample_rate:.3f} seconds)',
            ]
        )
    return '\n'.join(lines) + '\n'


def execute_autocalibrate(
    edit: AutocalibrateEdit, edit_directory: Path, destination: Path
) -> Path:
    prepared = prepare_autocalibrate(edit, edit_directory, destination)
    metadata = {
        'sources': {
            selector: {
                'session_id': source.session_id,
                'files': [f.path.as_posix() for f in source.fragments],
            }
            for selector, source in prepared.sources.items()
        }
    }
    return write_autocalibrate_session(
        prepared,
        destination,
        canonical_autocalibrate(prepared.edit),
        metadata,
    )


def materialized_autocalibrate_outputs(
    prepared: PreparedAutocalibrate,
) -> dict[str, MaterializedAudio]:
    return {
        prepared.track_ids[selector]: MaterializedAudio(
            source.samples,
            source.sample_rate,
            source.start_frame,
            [
                ObservedFrameRange(start=r.start, end=r.end)
                for r in prepared.intervals[selector]
            ],
        )
        for selector, source in prepared.audio.items()
    }


def autocalibrate_track_ids(selectors: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    used: list[str] = []
    for selector in selectors:
        identity = _unique_track_id(selector, used)
        used.append(identity)
        result[selector] = identity
    return result


def write_autocalibrate_session(
    prepared: PreparedAutocalibrate,
    destination: Path,
    edit_text: str,
    metadata: dict[str, object],
) -> Path:
    destination.mkdir(parents=True)
    (destination / 'edit.toml').write_text(edit_text)
    now = datetime.now(timezone.utc)
    writer = session_record.SessionRecordWriter(
        destination / 'session-record.jsonl',
        started_at=_timestamp(now),
        session_id=str(uuid.uuid4()),
        application={'name': 'recs edit'},
    )
    writer.write(
        session_record.EventRecord(
            type='edit_started',
            timestamp=_timestamp(now),
            path='edit.toml',
            metadata=metadata,
        ),
        sync=True,
    )
    try:
        for selector, source in prepared.audio.items():
            _write_track(
                writer,
                destination,
                prepared.track_ids[selector],
                source,
                prepared.intervals[selector],
                prepared.edit.output,
            )
    except (OSError, RecsError, soundfile.SoundFileError, KeyboardInterrupt) as e:
        message = 'Edit interrupted' if isinstance(e, KeyboardInterrupt) else str(e)
        try:
            writer.write(
                session_record.WarningRecord(
                    timestamp=_timestamp(datetime.now(timezone.utc)), message=message
                ),
                sync=True,
            )
        except OSError:
            pass
        finally:
            writer.close()
        raise
    ended = datetime.now(timezone.utc)
    writer.write(
        session_record.SessionFooter(
            ended_at=_timestamp(ended), duration_seconds=(ended - now).total_seconds()
        ),
        sync=True,
    )
    writer.close()
    return writer.path


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
            block = source.samples[
                start - source.start_frame : end - source.start_frame
            ]
            yield LevelWindow(
                start=start,
                end=end,
                level_dbfs=_level_dbfs(block, settings.analysis_floor_dbfs),
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


def _autocalibrate_from_options(
    record: Path | None,
    memory: str | None,
    channels: list[str],
    sample_rate: int,
    options: AutocalibrateOptions,
) -> AutocalibrateEdit:
    output_format = options.format or Format.flac
    subtype = options.subtype or (
        Subtype.pcm_24 if output_format == Format.flac else None
    )
    return AutocalibrateEdit(
        record=record,
        memory=memory,
        channels=channels,
        sample_rate=sample_rate,
        calibration=CalibrationSettings(
            window_frames=max(1, round(options.window_time * sample_rate)),
            candidate_percentile=options.candidate_percentile,
            candidate_tolerance_db=options.candidate_tolerance_db,
            minimum_silence_frames=max(
                1, round(options.minimum_silence_time * sample_rate)
            ),
            noise_percentile=options.noise_percentile,
            signal_margin_db=options.signal_margin_db,
            analysis_floor_dbfs=options.analysis_floor_dbfs,
        ),
        silence=SilenceSettings(
            quiet_before_frames=round(options.quiet_before * sample_rate),
            quiet_after_frames=round(options.quiet_after * sample_rate),
            stop_after_quiet_frames=round(options.stop_after_quiet * sample_rate),
            shortest_file_frames=round(options.shortest_file_time * sample_rate),
            longest_file_frames=round(options.longest_file_time * sample_rate),
        ),
        output=AutocalibrateOutput(format=output_format, subtype=subtype),
    )


def _prepare_materialized(
    edit: AutocalibrateEdit,
    sources: dict[str, ResolvedSource],
    audio: dict[str, MaterializedAudio],
    track_ids: dict[str, str],
    sample_rate: int,
) -> PreparedAutocalibrate:
    if edit.sample_rate is not None and edit.sample_rate != sample_rate:
        raise RecsError(
            f'Edit sample rate is {edit.sample_rate}, but sources use {sample_rate}'
        )
    _validate_output(edit.output, audio)
    thresholds = _thresholds(edit, audio)
    intervals = {
        selector: detect_intervals(
            level_windows_audio(audio[selector], edit.calibration),
            thresholds[selector],
            edit.silence,
        )
        for selector in audio
    }
    canonical = edit.model_copy(
        update={
            'channels': list(audio),
            'sample_rate': sample_rate,
            'thresholds': [thresholds[s] for s in audio],
        }
    )
    return PreparedAutocalibrate(
        edit=canonical,
        sources=sources,
        audio=audio,
        track_ids=track_ids,
        intervals=intervals,
    )


def _resolve_record_sources(
    record_path: Path, requested: list[str]
) -> tuple[dict[str, ResolvedSource], dict[str, str], int]:
    if not record_path.is_file():
        raise RecsError(f'Session record does not exist: {record_path}')
    record = session_record.read(record_path)
    if record.errors:
        raise RecsError('; '.join(record.errors))
    finished = [
        f
        for f in record.files
        if f.type == 'file_finished'
        and f.media_type == 'audio'
        and f.source is not None
        and f.track_name is not None
        and f.sample_rate is not None
        and f.channels is not None
        and f.frame_count is not None
        and f.quantity_count is not None
    ]
    available = list(dict.fromkeys(f'{f.source}:{f.track_name}' for f in finished))
    if not available:
        raise RecsError(f'No finished audio in {record_path}')
    selectors = requested or available
    if len(selectors) != len(set(selectors)):
        raise RecsError(f'Duplicate channel selectors: {selectors}')
    bases: dict[str, str] = {}
    for selector in selectors:
        if selector in available:
            bases[selector] = selector
            continue
        base, separator, offset = selector.rpartition(':')
        if not separator or not offset.isdigit() or base not in available:
            raise RecsError(
                f'Unknown channel selector {selector!r}; available: '
                + ', '.join(available)
            )
        bases[selector] = base
    sample_rates = {
        f.sample_rate
        for f in finished
        if f'{f.source}:{f.track_name}' in bases.values()
    }
    if len(sample_rates) != 1:
        raise RecsError(f'Selected tracks have mixed sample rates: {sample_rates}')
    sample_rate = next(iter(sample_rates))
    track_ids: dict[str, str] = {}
    used: list[str] = []
    specs: list[SourceSpec] = []
    for selector in selectors:
        identity = _unique_track_id(selector, used)
        used.append(identity)
        track_ids[selector] = identity
        specs.append(SourceSpec(id=identity, record=record_path, channel=selector))
    edit = EditSpec(schema_version=1, sample_rate=sample_rate, sources=specs)
    resolved = resolve_sources(edit, record_path.parent)
    return (
        {selector: resolved[track_ids[selector]] for selector in selectors},
        track_ids,
        sample_rate,
    )


def _validate_output(
    output: AutocalibrateOutput, sources: dict[str, MaterializedAudio]
) -> None:
    if output.format is None:
        return
    maximum = max(s.channels for s in sources.values())
    if output.format == Format.flac and maximum > 8:
        raise RecsError('FLAC supports at most 8 channels')
    if output.format == Format.mp3 and maximum > 2:
        raise RecsError('MP3 supports at most 2 channels')
    if not soundfile.check_format(output.format, output.subtype):
        detail = str(output.format)
        if output.subtype is not None:
            detail += f'/{output.subtype}'
        raise RecsError(f'Unsupported output format {detail}')


def _thresholds(
    edit: AutocalibrateEdit, sources: dict[str, MaterializedAudio]
) -> dict[str, CalibratedThreshold]:
    if edit.thresholds:
        result = {t.source: t for t in edit.thresholds}
        if len(result) != len(edit.thresholds):
            raise RecsError('Duplicate calibrated threshold selectors')
        if result.keys() != sources.keys():
            raise RecsError(
                'Calibrated threshold selectors do not match selected channels'
            )
        return result
    return {
        selector: calibrate_threshold(
            selector,
            lambda source=source: level_windows_audio(source, edit.calibration),
            edit.calibration,
        )
        for selector, source in sources.items()
    }


def _write_track(
    writer: session_record.SessionRecordWriter,
    destination: Path,
    track_id: str,
    source: MaterializedAudio,
    intervals: list[FrameRange],
    output: AutocalibrateOutput,
) -> None:
    if output.format is None:
        raise RecsError('Final autocalibration output requires format')
    for index, frame_range in enumerate(intervals, 1):
        relative = Path('audio') / track_id / f'{index:04d}.{output.format}'
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        now = _timestamp(datetime.now(timezone.utc))
        started = session_record.FileRecord(
            type='file_started',
            media_type='audio',
            timestamp=now,
            stream_id=f'audio:edit:{track_id}',
            format=output.format,
            frame_count=frame_range.start,
            path=relative.as_posix(),
            source='edit',
            track_name=track_id,
            source_channels=list(range(1, source.channels + 1)),
            channels=source.channels,
            sample_rate=source.sample_rate,
        )
        writer.write(started)
        try:
            fp = soundfile.SoundFile(
                path,
                mode='w',
                samplerate=source.sample_rate,
                channels=source.channels,
                format=output.format,
                subtype=output.subtype,
            )
        except soundfile.LibsndfileError as e:
            raise RecsError(f'Cannot create output {path}: {e}') from e
        try:
            fp.write(
                source.samples[
                    frame_range.start - source.start_frame : frame_range.end
                    - source.start_frame
                ]
            )
        finally:
            fp.close()
        with soundfile.SoundFile(path) as result:
            depth = bit_depth(result)
        writer.write(
            started.model_copy(
                update={
                    'type': 'file_finished',
                    'timestamp': _timestamp(datetime.now(timezone.utc)),
                    'frame_count': frame_range.end,
                    'quantity_count': frame_range.end - frame_range.start,
                    'bit_depth': depth,
                }
            )
        )


def _unique_track_id(selector: str, used: list[str]) -> str:
    value = re.sub('[^a-z0-9_-]+', '-', selector.lower()).strip('-_') or 'track'
    if not value[0].islower():
        value = f'track-{value}'
    base = value
    index = 2
    while value in used:
        value = f'{base}-{index}'
        index += 1
    return value


def _relative_path(path: Path, directory: Path) -> Path:
    try:
        return Path(os.path.relpath(path, directory))
    except ValueError:
        return path


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


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
