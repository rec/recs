import os
import re
from pathlib import Path

import soundfile
import tomlkit
from pydantic import BaseModel, ConfigDict, TypeAdapter
from reccy.configuration import units

from recs.base.errors import RecsError
from recs.base.types import Format, Subtype
from recs.edit.options import EditOptions
from recs.edit.schema import (
    AutomationPoint,
    AutomationSpec,
    BusSpec,
    ClipSpec,
    CommandKind,
    EditSpec,
    Interpolation,
    OutputSpec,
    RouteSpec,
    SourceSpec,
    TrackSpec,
    parse_edit,
    parse_partial_edit,
)
from recs.ui import session_record


class SessionRecordRequired(RecsError):
    pass


class _InputTrack(BaseModel, frozen=True):
    label: str
    selectors: list[str]
    source: SourceSpec
    channels: int
    sample_rate: int
    frame_count: int

    model_config = ConfigDict(extra='forbid')


def resolve_command(command: str, cwd: Path) -> tuple[dict[str, object], Path]:
    explicit = Path(command)
    if explicit.suffix == '.toml' or explicit.parent != Path('.'):
        path = (cwd / explicit).resolve()
        if not path.is_file():
            raise RecsError(f'Edit command file does not exist: {path}')
        return _resolve_file(path, discover_commands(cwd), []), path

    commands = discover_commands(cwd)
    paths = commands.get(command, [])
    if not paths:
        raise RecsError(f'Unknown edit command {command!r}')
    if len(paths) > 1:
        raise RecsError(
            f'Edit command {command!r} is defined more than once: '
            + ', '.join(str(p) for p in paths)
        )
    return _resolve_file(paths[0], commands, []), paths[0]


def discover_commands(cwd: Path) -> dict[str, list[Path]]:
    directories = [
        cwd / '.recs/edit',
        _user_config_directory() / 'recs/edit',
        Path(__file__).parent / 'commands',
    ]
    result: dict[str, list[Path]] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob('*.toml')):
            result.setdefault(path.stem, []).append(path.resolve())
    return result


def complete_or_generate(
    recipe: dict[str, object],
    input_paths: list[Path],
    options: EditOptions,
) -> EditSpec:
    text = tomlkit.dumps(recipe)
    try:
        return parse_edit(text)
    except ValueError:
        pass
    partial = parse_partial_edit(text)
    if partial.command is None or partial.command.operation is None:
        raise RecsError('Partial edit command has no _command.operation')
    if not input_paths:
        raise SessionRecordRequired('This edit command requires an input')
    generated = _generate(
        partial.command.operation,
        input_paths,
        options.channel,
        options.start,
        options.end,
        options.interval,
        options.format,
        options.subtype,
        options.route_gain,
        options.crossfade,
    )
    overlay = {k: v for k, v in recipe.items() if k not in {'extends', '_command'}}
    if outputs := overlay.pop('outputs', None):
        if not isinstance(outputs, list) or len(outputs) != 1:
            raise RecsError('Generated commands accept one [[outputs]] defaults table')
        defaults = _dictionary(outputs[0], 'Invalid [[outputs]] defaults table')
        generated_outputs = generated.get('outputs')
        if not isinstance(generated_outputs, list):
            raise RecsError('Generated command has invalid outputs')
        generated['outputs'] = [
            _merge(_dictionary(o, 'Generated command has invalid output'), defaults)
            for o in generated_outputs
        ]
    generated_outputs = generated.get('outputs')
    if not isinstance(generated_outputs, list):
        raise RecsError('Generated command has invalid outputs')
    overridden_outputs: list[dict[str, object]] = []
    for value in generated_outputs:
        output = _dictionary(value, 'Generated command has invalid output')
        if options.format is not None:
            output['format'] = options.format
            output['path'] = str(
                Path(str(output['path'])).with_suffix(f'.{options.format}')
            )
            if options.subtype is None:
                output.pop('subtype', None)
        if options.subtype is not None:
            output['subtype'] = options.subtype
        if options.normalize is not None:
            output['normalize'] = options.normalize
        if options.gain is not None:
            output['gain'] = options.gain
        overridden_outputs.append(output)
    generated['outputs'] = overridden_outputs
    return EditSpec.model_validate(_merge(generated, overlay))


def latest_record(cwd: Path) -> Path:
    records = list(cwd.rglob('session-record.jsonl'))
    if not records:
        raise RecsError(f'No session-record.jsonl found below {cwd}')
    return max(records, key=lambda p: p.stat().st_mtime)


def _resolve_file(
    path: Path, commands: dict[str, list[Path]], stack: list[Path]
) -> dict[str, object]:
    if path in stack:
        chain = ' -> '.join(str(p) for p in stack + [path])
        raise RecsError(f'Edit command inheritance cycle: {chain}')
    text = path.read_text()
    partial = parse_partial_edit(text)
    data = dict(tomlkit.parse(text))
    if not partial.extends:
        return data
    paths = commands.get(partial.extends, [])
    if len(paths) != 1:
        detail = 'not found' if not paths else ', '.join(str(p) for p in paths)
        raise RecsError(f'Extended command {partial.extends!r}: {detail}')
    return _merge(_resolve_file(paths[0], commands, stack + [path]), data)


def _merge(base: dict[str, object], overlay: dict[str, object]) -> dict[str, object]:
    result = dict(base)
    for key, value in overlay.items():
        previous = result.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            result[key] = _merge(
                _dictionary(previous, f'Invalid table {key}'),
                _dictionary(value, f'Invalid table {key}'),
            )
        else:
            result[key] = value
    return result


def _dictionary(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise RecsError(message)
    return {str(k): v for k, v in value.items()}


def _expand_input_paths(values: list[Path]) -> list[Path]:
    result: list[Path] = []
    for value in values:
        path = value.resolve()
        if path.is_file():
            if (
                path.name != 'session-record.jsonl'
                and path.suffix.lower() not in AUDIO_SUFFIXES
            ):
                raise RecsError(f'Unsupported edit input file: {path}')
            result.append(path)
            continue
        if not path.is_dir():
            raise RecsError(f'Edit input does not exist: {path}')
        if (record := path / 'session-record.jsonl').is_file():
            result.append(record)
            continue
        media = sorted(
            p
            for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES
        )
        records = sorted(path.rglob('session-record.jsonl'))
        if media and records:
            raise RecsError(f'Edit input directory mixes media and sessions: {path}')
        if media:
            result.extend(media)
        elif len(records) == 1:
            result.extend(records)
        elif records:
            raise RecsError(
                f'Edit input directory contains multiple session records: {path}'
            )
        else:
            raise RecsError(f'Edit input directory contains no supported audio: {path}')
    return result


def _input_tracks(paths: list[Path]) -> list[_InputTrack]:
    result: list[_InputTrack] = []
    identifiers: list[str] = []
    qualify = len(paths) > 1
    for path in paths:
        name = path.parent.name if path.name == 'session-record.jsonl' else path.stem
        input_id = _unique_identifier(name, identifiers)
        identifiers.append(input_id)
        if path.name == 'session-record.jsonl':
            result.extend(_record_tracks(path, input_id, qualify))
        else:
            result.append(_file_track(path, input_id))
    if not result:
        raise RecsError('Edit inputs contain no audio tracks')
    return result


def _record_tracks(path: Path, input_id: str, qualify: bool) -> list[_InputTrack]:
    record = session_record.read(path)
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
    result: list[_InputTrack] = []
    selectors = list(dict.fromkeys(f'{f.source}:{f.track_name}' for f in finished))
    for selector in selectors:
        files = [f for f in finished if f'{f.source}:{f.track_name}' == selector]
        widths = {f.channels for f in files}
        rates = {f.sample_rate for f in files}
        if len(widths) != 1 or len(rates) != 1:
            raise RecsError(f'Inconsistent audio metadata for {selector} in {path}')
        label = f'{input_id}:{selector}' if qualify else selector
        result.append(
            _InputTrack(
                label=label,
                selectors=[label],
                source=SourceSpec(id='source', record=path, channel=selector),
                channels=next(iter(widths)),
                sample_rate=next(iter(rates)),
                frame_count=max(
                    f.frame_count for f in files if f.frame_count is not None
                ),
            )
        )
    if not result:
        raise RecsError(f'No finished audio in {path}')
    return result


def _file_track(path: Path, input_id: str) -> _InputTrack:
    try:
        info = soundfile.info(path)
    except soundfile.LibsndfileError as e:
        raise RecsError(f'Cannot read edit input {path}: {e}') from e
    return _InputTrack(
        label=input_id,
        selectors=[input_id],
        source=SourceSpec(
            id='source', file=path, channels=list(range(1, info.channels + 1))
        ),
        channels=info.channels,
        sample_rate=info.samplerate,
        frame_count=info.frames,
    )


def _select_tracks(
    tracks: list[_InputTrack], selectors: list[str]
) -> list[_InputTrack]:
    if not selectors:
        return tracks
    result: list[_InputTrack] = []
    for selector in selectors:
        exact = [t for t in tracks if selector in t.selectors]
        if len(exact) == 1:
            result.append(exact[0])
            continue
        base, separator, text_channel = selector.rpartition(':')
        candidates = [t for t in tracks if base in t.selectors]
        if separator and text_channel.isdigit() and len(candidates) == 1:
            result.append(_mono_track(candidates[0], int(text_channel), selector))
            continue
        available = ', '.join(t.label for t in tracks)
        raise RecsError(
            f'Unknown channel selectors: {selector!r}; available: {available}'
        )
    return result


def _mono_tracks(track: _InputTrack) -> list[_InputTrack]:
    if track.channels == 1:
        return [track]
    return [
        _mono_track(track, channel, f'{track.label}:{channel}')
        for channel in range(1, track.channels + 1)
    ]


def _mono_track(track: _InputTrack, channel: int, label: str) -> _InputTrack:
    if not 1 <= channel <= track.channels:
        raise RecsError(
            f'Channel {channel} exceeds width {track.channels}: {track.label}'
        )
    source = track.source
    if source.record is not None:
        assert source.channel is not None
        source = source.model_copy(update={'channel': f'{source.channel}:{channel}'})
    else:
        source = source.model_copy(update={'channels': [source.channels[channel - 1]]})
    return track.model_copy(
        update={'label': label, 'selectors': [label], 'source': source, 'channels': 1}
    )


def _generate(
    operation: CommandKind,
    input_paths: list[Path],
    requested_selectors: list[str],
    start_seconds: float,
    end_seconds: float | None,
    intervals: list[str],
    output_format: Format | None,
    subtype: Subtype | None,
    route_gains: list[float],
    crossfade: float | None,
) -> dict[str, object]:
    paths = _expand_input_paths(input_paths)
    input_tracks = _input_tracks(paths)
    selected = _select_tracks(input_tracks, requested_selectors)
    if operation == CommandKind.split:
        selected = [m for t in selected for m in _mono_tracks(t)]
    sample_rates = {t.sample_rate for t in selected}
    if len(sample_rates) != 1:
        raise RecsError(f'Inputs have mixed sample rates: {sorted(sample_rates)}')
    sample_rate = next(iter(sample_rates))
    output_format = output_format or Format.flac
    format_subtype = subtype or (
        Subtype.pcm_24 if output_format == Format.flac else None
    )
    sources: list[SourceSpec] = []
    output_tracks: list[TrackSpec] = []
    clips: list[ClipSpec] = []
    outputs: list[OutputSpec] = []
    identifiers: list[str] = []
    timeline_start = 0
    for input_index, input_track in enumerate(selected):
        identity = _unique_identifier(input_track.label, identifiers)
        identifiers.append(identity)
        source_id = f'{identity}-source'
        sources.append(input_track.source.model_copy(update={'id': source_id}))
        ranges = _input_ranges(
            operation,
            input_index,
            len(selected),
            input_track.frame_count,
            sample_rate,
            start_seconds,
            end_seconds,
            intervals,
        )
        track_id = 'stitch' if operation == CommandKind.stitch else identity
        if operation != CommandKind.stitch:
            output_tracks.append(TrackSpec(id=track_id, channels=input_track.channels))
        for range_index, (source_start, source_end) in enumerate(ranges):
            clips.append(
                ClipSpec(
                    id=f'{identity}-{range_index + 1}',
                    source=source_id,
                    track=track_id,
                    source_start=source_start,
                    source_end=source_end,
                    timeline_start=(
                        timeline_start
                        if operation == CommandKind.stitch
                        else source_start - ranges[0][0]
                    ),
                )
            )
            if operation == CommandKind.stitch:
                timeline_start += source_end - source_start
        if operation not in (CommandKind.mix, CommandKind.stitch):
            outputs.append(
                OutputSpec(
                    id=identity,
                    source=track_id,
                    path=Path(f'audio/{identity}.{output_format}'),
                    format=output_format,
                    subtype=format_subtype,
                )
            )
    if operation == CommandKind.stitch:
        widths = {t.channels for t in selected}
        if len(widths) != 1:
            raise RecsError('Stitch inputs must have matching channel widths')
        output_tracks = [TrackSpec(id='stitch', channels=next(iter(widths)))]
        outputs = [
            OutputSpec(
                id='stitch',
                source='stitch',
                path=Path(f'audio/stitch.{output_format}'),
                format=output_format,
                subtype=format_subtype,
            )
        ]
    buses: list[BusSpec] = []
    routes: list[RouteSpec] = []
    automation: list[AutomationSpec] = []
    if operation == CommandKind.mix:
        widths = {t.channels for t in output_tracks}
        if len(widths) != 1:
            raise RecsError('Mix inputs must have matching channel widths')
        buses = [BusSpec(id='master', channels=next(iter(widths)))]
        if route_gains and len(route_gains) != len(output_tracks):
            raise RecsError('Mix requires one --route-gain for each selected channel')
        gains = route_gains or [1.0] * len(output_tracks)
        routes = [
            RouteSpec(source=t.id, destination='master', gain=g)
            for t, g in zip(output_tracks, gains, strict=False)
        ]
        if crossfade is not None:
            if len(routes) != 2:
                raise RecsError('--crossfade requires exactly two selected channels')
            fade_end = round(crossfade * sample_rate)
            if fade_end <= 0:
                raise RecsError('--crossfade must be greater than zero')
            automation = [
                AutomationSpec(
                    target=f'route:{routes[0].source}->master:gain',
                    interpolation=Interpolation.equal_power,
                    points=[
                        AutomationPoint(frame=0, value=routes[0].gain),
                        AutomationPoint(frame=fade_end, value=0),
                    ],
                ),
                AutomationSpec(
                    target=f'route:{routes[1].source}->master:gain',
                    interpolation=Interpolation.equal_power,
                    points=[
                        AutomationPoint(frame=0, value=0),
                        AutomationPoint(frame=fade_end, value=routes[1].gain),
                    ],
                ),
            ]
        outputs = [
            OutputSpec(
                id='mix',
                source='master',
                path=Path(f'audio/mix.{output_format}'),
                format=output_format,
                subtype=format_subtype,
            )
        ]
    return EditSpec(
        schema_version=1,
        sample_rate=sample_rate,
        sources=sources,
        tracks=output_tracks,
        buses=buses,
        clips=clips,
        routes=routes,
        automation=automation,
        outputs=outputs,
    ).model_dump(mode='json', exclude_none=True)


def _input_ranges(
    operation: CommandKind,
    input_index: int,
    input_count: int,
    frame_count: int,
    sample_rate: int,
    start_seconds: float,
    end_seconds: float | None,
    intervals: list[str],
) -> list[tuple[int, int]]:
    if operation == CommandKind.stitch and intervals:
        if input_count == 1:
            result = [_parse_interval(v, sample_rate) for v in intervals]
        elif len(intervals) == input_count:
            result = [_parse_interval(intervals[input_index], sample_rate)]
        else:
            raise RecsError(
                'Stitch requires one --interval per input when using multiple inputs'
            )
    else:
        start = round(start_seconds * sample_rate)
        end = frame_count if end_seconds is None else round(end_seconds * sample_rate)
        result = [(start, end)]
    if any(a < 0 or b <= a or b > frame_count for a, b in result):
        raise RecsError(f'Invalid source intervals: {result}')
    return result


def _parse_interval(value: str, sample_rate: int) -> tuple[int, int]:
    try:
        start, end = value.split(':', 1)
        adapter = TypeAdapter(units.Seconds)
        return (
            round(adapter.validate_python(start) * sample_rate),
            round(adapter.validate_python(end) * sample_rate),
        )
    except ValueError:
        raise RecsError(f'Invalid interval {value!r}; expected START:END') from None


def _unique_identifier(selector: str, existing: list[str]) -> str:
    base = re.sub('[^a-z0-9_-]+', '-', selector.lower()).strip('-_') or 'track'
    if not base[0].islower():
        base = f'track-{base}'
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f'{base}-{index}'
        index += 1
    return candidate


def _user_config_directory() -> Path:
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))


AUDIO_SUFFIXES = {f'.{f}' for f in Format if f != Format.raw}
