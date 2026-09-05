import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel, ConfigDict, Field
from reccy import config, units

from recs.base.errors import RecsError
from recs.base.types import Format, Subtype
from recs.edit import commands
from recs.edit.schema import NormalizeMode
from recs.edit.session import execute_edit
from recs.ui import recording_paths

TIME_SPEC = config.unit_spec(units.Seconds, 'TIME')


class EditCli(BaseModel, frozen=True):
    record: Annotated[Path | None, tyro.conf.Positional] = None

    destination: Annotated[
        Path | None,
        tyro.conf.arg(aliases=('-o',), help='New output session directory'),
    ] = None

    channel: Annotated[
        list[str], tyro.conf.arg(help='SOURCE:TRACK selector; repeat to select several')
    ] = Field(default_factory=list)

    start: Annotated[
        units.Seconds,
        TIME_SPEC,
        tyro.conf.arg(help='Start time within the source'),
    ] = 0

    end: Annotated[
        units.Seconds | None,
        TIME_SPEC,
        tyro.conf.arg(help='End time within the source'),
    ] = None

    interval: Annotated[
        list[str],
        tyro.conf.arg(help='START:END source interval; repeat for stitch'),
    ] = Field(default_factory=list)

    format: Format | None = None

    subtype: Subtype | None = None

    normalize: NormalizeMode | None = None

    gain: float | None = None

    route_gain: Annotated[
        list[float], tyro.conf.arg(help='Initial gain for each selected mix route')
    ] = Field(default_factory=list)

    crossfade: Annotated[
        units.Seconds | None,
        TIME_SPEC,
        tyro.conf.arg(help='Crossfade the first two selected mix routes'),
    ] = None

    model_config = ConfigDict(extra='forbid')


def main(args: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if args is None else args)
    if not args:
        raise RecsError('Expected an edit command name or TOML path')
    command = args.pop(0)
    cwd = Path.cwd()
    recipe, command_path = commands.resolve_command(command, cwd)
    cfg = tyro.cli(EditCli, args=args, prog=f'recs edit {command}')
    record_path = cfg.record
    try:
        complete = commands.complete_or_generate(
            recipe,
            record_path,
            cfg.channel,
            cfg.start,
            cfg.end,
            cfg.interval,
            cfg.format,
            cfg.subtype,
            cfg.normalize,
            cfg.gain,
            cfg.route_gain,
            cfg.crossfade,
        )
    except commands.SessionRecordRequired:
        record_path = commands.latest_record(cwd)
        complete = commands.complete_or_generate(
            recipe,
            record_path,
            cfg.channel,
            cfg.start,
            cfg.end,
            cfg.interval,
            cfg.format,
            cfg.subtype,
            cfg.normalize,
            cfg.gain,
            cfg.route_gain,
            cfg.crossfade,
        )
    destination = cfg.destination or recording_paths.available_directory(
        cwd / f'{datetime.now():%Y-%m-%d %H-%M-%S} edit'
    )
    print(f'Command: {command} ({command_path})')
    print(f'Record: {record_path or "declared by edit TOML"}')
    print(f'Media types: {", ".join(complete.media_types)}')
    print(f'Sample rate: {complete.sample_rate}')
    print(f'Channels: {", ".join(s.channel for s in complete.sources)}')
    print(f'Tracks: {", ".join(t.id for t in complete.tracks)}')
    print(f'Buses: {", ".join(b.id for b in complete.buses) or "none"}')
    print(f'Output session: {destination}')
    for output in complete.outputs:
        start = output.start or 0
        end = output.end if output.end is not None else 'arrangement end'
        print(f'Output: {output.path} ({output.format}, frames {start}:{end})')
    execute_edit(complete, command_path.parent, destination)
    return 0
