from pathlib import Path

import pytest

from recs.base.errors import RecsError
from recs.base.types import Format
from recs.edit.commands import complete_or_generate, discover_commands, resolve_command
from recs.ui import session_record


def test_packaged_commands_are_discovered(tmp_path: Path) -> None:
    commands = discover_commands(tmp_path)

    assert {'clip', 'stitch', 'split', 'mix'} <= commands.keys()


def test_command_lists_replace_and_tables_merge(tmp_path: Path) -> None:
    directory = tmp_path / '.recs/edit'
    directory.mkdir(parents=True)
    (directory / 'base.toml').write_text(
        """
schema_version = 1
media_types = ["audio", "midi"]
[_command]
help = "base"
operation = "clip"
"""
    )
    path = directory / 'derived.toml'
    path.write_text(
        """
extends = "base"
media_types = ["audio"]
[_command]
help = "derived"
"""
    )

    result, result_path = resolve_command('derived', tmp_path)

    assert result_path == path
    assert result['media_types'] == ['audio']
    assert result['_command'] == {'help': 'derived', 'operation': 'clip'}


def test_named_command_collisions_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / '.recs/edit'
    directory.mkdir(parents=True)
    (directory / 'clip.toml').write_text('[_command]\noperation = "clip"\n')

    with pytest.raises(RecsError, match='defined more than once'):
        resolve_command('clip', tmp_path)


def test_command_inheritance_cycles_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / '.recs/edit'
    directory.mkdir(parents=True)
    (directory / 'one.toml').write_text('extends = "two"\n')
    (directory / 'two.toml').write_text('extends = "one"\n')

    with pytest.raises(RecsError, match='inheritance cycle'):
        resolve_command('one', tmp_path)


@pytest.mark.parametrize(
    ('command', 'output_count', 'bus_count'),
    [('clip', 2, 0), ('stitch', 2, 0), ('split', 2, 0), ('mix', 1, 1)],
)
def test_builtins_generate_complete_arrangements(
    tmp_path: Path, command: str, output_count: int, bus_count: int
) -> None:
    record_path = _record(tmp_path)
    recipe, _ = resolve_command(command, tmp_path)

    edit = complete_or_generate(
        recipe,
        record_path,
        [],
        0,
        None,
        [],
        Format.wav,
        None,
        None,
        None,
        [],
        None,
    )

    assert len(edit.sources) == 2
    assert len(edit.outputs) == output_count
    assert len(edit.buses) == bus_count


def test_generated_arrangement_accepts_mono_offset(tmp_path: Path) -> None:
    record_path = _record(tmp_path)
    recipe, _ = resolve_command('clip', tmp_path)

    edit = complete_or_generate(
        recipe,
        record_path,
        ['device:pair:2'],
        0,
        None,
        [],
        Format.wav,
        None,
        None,
        None,
        [],
        None,
    )

    assert edit.sources[0].channel == 'device:pair:2'
    assert edit.tracks[0].channels == 1


def test_mix_generates_route_gains_and_crossfade(tmp_path: Path) -> None:
    record_path = _record(tmp_path)
    recipe, _ = resolve_command('mix', tmp_path)

    edit = complete_or_generate(
        recipe,
        record_path,
        [],
        0,
        None,
        [],
        None,
        None,
        None,
        None,
        [0.75, 0.5],
        0.25,
    )

    assert [r.gain for r in edit.routes] == [0.75, 0.5]
    assert len(edit.automation) == 2
    assert edit.automation[0].points[-1].frame == 12_000


def _record(directory: Path) -> Path:
    path = directory / 'session-record.jsonl'
    writer = session_record.SessionRecordWriter(path, started_at='start')
    for source, track in [('device', 'pair'), ('room', 'pair')]:
        values = {
            'media_type': 'audio',
            'stream_id': f'audio:{source}:1-2',
            'format': 'wav',
            'path': f'{source}.wav',
            'source': source,
            'track_name': track,
            'source_channels': [1, 2],
            'channels': 2,
            'sample_rate': 48_000,
            'bit_depth': 32,
        }
        writer.write(
            session_record.FileRecord(
                type='file_started', timestamp='start', frame_count=0, **values
            )
        )
        writer.write(
            session_record.FileRecord(
                type='file_finished',
                timestamp='end',
                frame_count=48_000,
                quantity_count=48_000,
                **values,
            )
        )
    writer.close()
    return path
