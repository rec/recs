from pathlib import Path

import soundfile
from pydantic import BaseModel, ConfigDict

from recs.base.errors import RecsError
from recs.base.types import Format
from recs.edit.schema import EditSpec, SourceSpec
from recs.ui import session_record


class AudioFragment(BaseModel, frozen=True):
    path: Path
    start: int
    end: int
    channels: int
    channel_offset: int = 0

    model_config = ConfigDict(extra='forbid')


class ResolvedSource(BaseModel, frozen=True):
    id: str
    record: Path | None
    file: Path | None
    session_id: str | None
    selector: str
    channels: int
    sample_rate: int
    timeline_end: int
    fragments: list[AudioFragment]

    model_config = ConfigDict(extra='forbid')


def resolve_sources(edit: EditSpec, edit_directory: Path) -> dict[str, ResolvedSource]:
    resolved = {
        source.id: _resolve_source(source, edit_directory) for source in edit.sources
    }
    wrong_rates = [
        f'{s.id}: {s.sample_rate}'
        for s in resolved.values()
        if s.sample_rate != edit.sample_rate
    ]
    if wrong_rates:
        raise RecsError(
            f'Edit sample rate is {edit.sample_rate}, but sources have '
            + ', '.join(wrong_rates)
        )
    return resolved


def _resolve_source(source: SourceSpec, edit_directory: Path) -> ResolvedSource:
    if source.file is not None:
        return _resolve_file_source(source, edit_directory)
    assert source.record is not None
    assert source.channel is not None
    record_path = (edit_directory / source.record).resolve()
    if not record_path.is_file():
        raise RecsError(
            f'Source {source.id}: session record does not exist: {record_path}'
        )
    record = session_record.read(record_path)
    if record.errors:
        raise RecsError(f'Source {source.id}: ' + '; '.join(record.errors))

    source_name, track_name, offset = _parse_selector(source.channel)
    files = [
        f
        for f in record.files
        if f.type == 'file_finished'
        and f.media_type == 'audio'
        and f.source == source_name
        and f.track_name == track_name
    ]
    if not files:
        raise RecsError(
            f'Source {source.id}: selector {source.channel!r} matches no finished audio'
        )
    _validate_started_files(source.id, files, record.files)
    fragments, width, sample_rate = _select_fragments(
        source, files, record_path.parent, offset
    )
    timeline_end = max(f.end for f in fragments)
    timeline_end = max(
        timeline_end,
        max(
            (
                f.frame_count or 0
                for f in record.files
                if f.type == 'file_finished'
                and f.media_type == 'audio'
                and f.source == source_name
            ),
            default=0,
        ),
    )
    if record.duration_seconds is not None:
        timeline_end = max(timeline_end, round(record.duration_seconds * sample_rate))
    return ResolvedSource(
        id=source.id,
        record=record_path,
        file=None,
        session_id=record.session_id,
        selector=source.channel,
        channels=width,
        sample_rate=sample_rate,
        timeline_end=timeline_end,
        fragments=fragments,
    )


def _resolve_file_source(source: SourceSpec, edit_directory: Path) -> ResolvedSource:
    assert source.file is not None
    path = (edit_directory / source.file).resolve()
    if not path.is_file():
        raise RecsError(f'Source {source.id}: audio file does not exist: {path}')
    try:
        info = soundfile.info(path)
    except soundfile.LibsndfileError as e:
        raise RecsError(f'Source {source.id}: cannot read {path}: {e}') from e
    first = source.channels[0] - 1
    if source.channels[-1] > info.channels:
        raise RecsError(
            f'Source {source.id}: channel {source.channels[-1]} exceeds '
            f'file width {info.channels}'
        )
    return ResolvedSource(
        id=source.id,
        record=None,
        file=path,
        session_id=None,
        selector=f'{path.name}:{source.channels[0]}-{source.channels[-1]}',
        channels=len(source.channels),
        sample_rate=info.samplerate,
        timeline_end=info.frames,
        fragments=[
            AudioFragment(
                path=path,
                start=0,
                end=info.frames,
                channels=len(source.channels),
                channel_offset=first,
            )
        ],
    )


def _validate_started_files(
    source_id: str,
    finished: list[session_record.FileRecord],
    all_files: list[session_record.FileRecord],
) -> None:
    started = [f for f in all_files if f.type == 'file_started']
    for file in finished:
        if file.frame_count is None or file.quantity_count is None:
            raise RecsError(f'Source {source_id}: incomplete range for {file.path}')
        matches = [
            f
            for f in started
            if f.path == file.path
            and f.stream_id == file.stream_id
            and f.frame_count is not None
            and f.frame_count == file.frame_count - file.quantity_count
        ]
        if len(matches) != 1:
            raise RecsError(
                f'Source {source_id}: {file.path} has {len(matches)} matching '
                'file_started records'
            )


def _parse_selector(selector: str) -> tuple[str, str, int | None]:
    parts = selector.rsplit(':', 2)
    if len(parts) < 2:
        raise RecsError(
            f'Invalid source selector {selector!r}; expected SOURCE:TRACK[:OFFSET]'
        )
    if len(parts) == 3 and parts[-1].isdigit():
        source, track, text_offset = parts
        offset = int(text_offset)
        if offset < 1:
            raise RecsError(f'Invalid channel offset in selector {selector!r}')
        return source, track, offset
    source, track = selector.rsplit(':', 1)
    return source, track, None


def _select_fragments(
    source: SourceSpec,
    files: list[session_record.FileRecord],
    record_directory: Path,
    offset: int | None,
) -> tuple[list[AudioFragment], int, int]:
    variants: dict[tuple[int, int], list[session_record.FileRecord]] = {}
    for file in files:
        if (
            file.frame_count is None
            or file.quantity_count is None
            or file.channels is None
            or file.sample_rate is None
        ):
            raise RecsError(
                f'Source {source.id}: incomplete audio metadata for {file.path}'
            )
        start = file.frame_count - file.quantity_count
        if start < 0:
            raise RecsError(f'Source {source.id}: invalid frame range for {file.path}')
        variants.setdefault((start, file.frame_count), []).append(file)

    ranges = sorted(variants)
    if any(a[1] > b[0] for a, b in zip(ranges, ranges[1:], strict=False)):
        raise RecsError(f'Source {source.id}: overlapping source file ranges: {ranges}')

    selected: list[session_record.FileRecord] = []
    for frame_range in ranges:
        choices = variants[frame_range]
        if source.input_format is not None:
            choices = [f for f in choices if f.format == source.input_format]
        else:
            choices = _preferred_variants(choices)
        if len(choices) != 1:
            names = ', '.join(f.path for f in variants[frame_range])
            raise RecsError(
                f'Source {source.id}: ambiguous variants for frames '
                f'{frame_range[0]}:{frame_range[1]}: {names}'
            )
        selected.append(choices[0])

    widths = {f.channels for f in selected}
    rates = {f.sample_rate for f in selected}
    if len(widths) != 1 or len(rates) != 1:
        raise RecsError(f'Source {source.id}: inconsistent audio metadata')
    file_width = next(iter(widths))
    width = 1 if offset is not None else file_width
    channel_offset = 0 if offset is None else offset - 1
    if channel_offset >= file_width:
        raise RecsError(
            f'Source {source.id}: channel offset {offset} exceeds width {file_width}'
        )

    fragments = [
        AudioFragment(
            path=_contained_file(record_directory, f.path, source.id),
            start=frame_range[0],
            end=frame_range[1],
            channels=width,
            channel_offset=channel_offset,
        )
        for frame_range, f in zip(ranges, selected, strict=False)
    ]
    for fragment in fragments:
        try:
            info = soundfile.info(fragment.path)
        except soundfile.LibsndfileError as e:
            raise RecsError(
                f'Source {source.id}: cannot read {fragment.path}: {e}'
            ) from e
        expected_frames = fragment.end - fragment.start
        if (
            info.frames != expected_frames
            or info.channels != file_width
            or info.samplerate != next(iter(rates))
        ):
            raise RecsError(
                f'Source {source.id}: file metadata disagrees with record: '
                f'{fragment.path}'
            )
    return fragments, width, next(iter(rates))


def _preferred_variants(
    choices: list[session_record.FileRecord],
) -> list[session_record.FileRecord]:
    for format in Format:
        result = [f for f in choices if f.format == format]
        if result:
            return result
    return choices


def _contained_file(directory: Path, value: str, source_id: str) -> Path:
    path = (directory / value).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise RecsError(
            f'Source {source_id}: audio path escapes record directory: {value}'
        )
    if not path.is_file():
        raise RecsError(f'Source {source_id}: audio file does not exist: {path}')
    return path
