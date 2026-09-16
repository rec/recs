import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import soundfile
import tomlkit
from ufor.encoding import Format, Subtype
from ufor.references import RecordSelector

from recs.base.errors import RecsError
from recs.edit.calibration_analysis import (
    calibrate_threshold,
    detect_intervals,
    level_windows_audio,
)
from recs.edit.calibration_schema import (
    AutocalibrateEdit,
    AutocalibrateOptions,
    AutocalibrateOutput,
    CalibratedThreshold,
    CalibrationSettings,
    FrameRange,
    PreparedAutocalibrate,
    SilenceSettings,
)
from recs.edit.commands import input_tracks
from recs.edit.graph import FrameRange as ObservedFrameRange
from recs.edit.inputs import SourceSpec
from recs.edit.materialized import MaterializedAudio, SourceMaterializer
from recs.edit.output import bit_depth
from recs.edit.record import ResolvedSource, resolve_input
from recs.recording import session_record
from recs.recording.finalize import finalize_recording


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
            source.storage,
            source.sample_rate,
            source.start_frame,
            [
                ObservedFrameRange(start=r.start, end=r.end)
                for r in prepared.intervals[selector]
            ],
            storage_start=source.storage_start,
            frames=source.end_frame - source.start_frame,
            channel_start=source.channel_start,
            channels=source.channels,
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
    return finalize_recording(writer.path)


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
    tracks = input_tracks([record_path])
    available = [t.label for t in tracks]
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
    sample_rates = {t.sample_rate for t in tracks if t.label in bases.values()}
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
        track = next(t for t in tracks if t.label == bases[selector])
        assert track.source.selector is not None
        channel = (
            None if selector == bases[selector] else int(selector.rsplit(':', 1)[1]) - 1
        )
        specs.append(
            SourceSpec(
                name=identity,
                record=record_path,
                selector=RecordSelector(
                    source=track.source.selector.source,
                    track=track.source.selector.track,
                    channel=channel,
                ),
            )
        )
    resolved = {s.name: resolve_input(s, record_path.parent) for s in specs}
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
        started = session_record.AudioFileRecord(
            clock_id='audio',
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
            for block in source.blocks(frame_range.start, frame_range.end):
                fp.write(block)
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
