import os
import re
from pathlib import Path

import tomlkit
from pydantic import TypeAdapter
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
    record_path: Path | None,
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
    if record_path is None:
        raise SessionRecordRequired('This edit command requires a session record')
    generated = _generate(
        partial.command.operation,
        record_path,
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


def _generate(
    operation: CommandKind,
    record_path: Path,
    requested_selectors: list[str],
    start_seconds: float,
    end_seconds: float | None,
    intervals: list[str],
    output_format: Format | None,
    subtype: Subtype | None,
    route_gains: list[float],
    crossfade: float | None,
) -> dict[str, object]:
    record_path = record_path.resolve()
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
    if not finished:
        raise RecsError(f'No finished audio in {record_path}')
    sample_rates = {f.sample_rate for f in finished}
    if len(sample_rates) != 1:
        raise RecsError(f'Mixed sample rates in {record_path}: {sample_rates}')
    sample_rate = next(iter(sample_rates))
    available = list(dict.fromkeys(f'{f.source}:{f.track_name}' for f in finished))
    selectors = requested_selectors or available
    unknown = [s for s in selectors if _selector_base(s) not in available]
    if unknown:
        raise RecsError(f'Unknown channel selectors: {unknown}; available: {available}')
    ranges = _ranges(
        operation, start_seconds, end_seconds, intervals, sample_rate, finished
    )
    output_format = output_format or Format.flac
    format_subtype = subtype or (
        Subtype.pcm_24 if output_format == Format.flac else None
    )
    sources: list[SourceSpec] = []
    tracks: list[TrackSpec] = []
    clips: list[ClipSpec] = []
    outputs: list[OutputSpec] = []
    identifiers: list[str] = []
    for selector in selectors:
        identity = _unique_identifier(selector, identifiers)
        identifiers.append(identity)
        base_selector = _selector_base(selector)
        file_width = next(
            f.channels
            for f in finished
            if f'{f.source}:{f.track_name}' == base_selector
        )
        offset = _selector_offset(selector)
        if offset is not None and offset > file_width:
            raise RecsError(
                f'Channel offset {offset} exceeds width {file_width}: {selector}'
            )
        width = 1 if offset is not None else file_width
        sources.append(
            SourceSpec(id=f'{identity}-source', record=record_path, channel=selector)
        )
        tracks.append(TrackSpec(id=identity, channels=width))
        timeline_start = 0
        for range_index, (source_start, source_end) in enumerate(ranges):
            clips.append(
                ClipSpec(
                    id=f'{identity}-{range_index + 1}',
                    source=f'{identity}-source',
                    track=identity,
                    source_start=source_start,
                    source_end=source_end,
                    timeline_start=(
                        timeline_start
                        if operation == CommandKind.stitch
                        else source_start - ranges[0][0]
                    ),
                )
            )
            timeline_start += source_end - source_start
        if operation != CommandKind.mix:
            outputs.append(
                OutputSpec(
                    id=identity,
                    source=identity,
                    path=Path(f'audio/{identity}.{output_format}'),
                    format=output_format,
                    subtype=format_subtype,
                )
            )
    buses: list[BusSpec] = []
    routes: list[RouteSpec] = []
    automation: list[AutomationSpec] = []
    if operation == CommandKind.mix:
        widths = {t.channels for t in tracks}
        if len(widths) != 1:
            raise RecsError('Mix inputs must have matching channel widths')
        buses = [BusSpec(id='master', channels=next(iter(widths)))]
        if route_gains and len(route_gains) != len(tracks):
            raise RecsError('Mix requires one --route-gain for each selected channel')
        gains = route_gains or [1.0] * len(tracks)
        routes = [
            RouteSpec(source=t.id, destination='master', gain=g)
            for t, g in zip(tracks, gains, strict=False)
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
        tracks=tracks,
        buses=buses,
        clips=clips,
        routes=routes,
        automation=automation,
        outputs=outputs,
    ).model_dump(mode='json', exclude_none=True)


def _ranges(
    operation: CommandKind,
    start_seconds: float,
    end_seconds: float | None,
    intervals: list[str],
    sample_rate: int,
    files: list[session_record.FileRecord],
) -> list[tuple[int, int]]:
    last_frame = max(f.frame_count or 0 for f in files)
    if operation == CommandKind.stitch and intervals:
        result = [_parse_interval(v, sample_rate) for v in intervals]
    else:
        start = round(start_seconds * sample_rate)
        end = last_frame if end_seconds is None else round(end_seconds * sample_rate)
        result = [(start, end)]
    if any(a < 0 or b <= a for a, b in result):
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


def _selector_base(selector: str) -> str:
    parts = selector.rsplit(':', 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else selector


def _selector_offset(selector: str) -> int | None:
    parts = selector.rsplit(':', 1)
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    offset = int(parts[1])
    if offset < 1:
        raise RecsError(f'Invalid channel offset: {selector}')
    return offset


def _user_config_directory() -> Path:
    if os.name == 'nt':
        return Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
