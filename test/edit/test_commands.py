from pathlib import Path

import numpy as np
import pytest
import soundfile
from ufor.encoding import Format

from recs.base.errors import RecsError
from recs.edit.commands import complete_or_generate, discover_commands, resolve_command
from recs.edit.options import EditOptions
from recs.recording.finalize import finalize_recording
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
    ('command', 'source_count', 'output_count', 'bus_count'),
    [
        ('clip', 2, 2, 0),
        ('stitch', 2, 1, 0),
        ('split', 4, 4, 0),
        ('mix', 2, 1, 1),
    ],
)
def test_builtins_generate_complete_arrangements(
    tmp_path: Path,
    command: str,
    source_count: int,
    output_count: int,
    bus_count: int,
) -> None:
    record_path = _record(tmp_path)
    recipe, _ = resolve_command(command, tmp_path)

    edit = complete_or_generate(
        recipe,
        [record_path],
        EditOptions(format=Format.wav),
    )

    assert len(edit.body.sources) == source_count
    assert len(edit.body.outputs) == output_count
    assert len(edit.body.buses) == bus_count


def test_generated_arrangement_accepts_mono_offset(tmp_path: Path) -> None:
    record_path = _record(tmp_path)
    recipe, _ = resolve_command('clip', tmp_path)

    edit = complete_or_generate(
        recipe,
        [record_path],
        EditOptions(channel=['device:pair:2'], format=Format.wav),
    )

    assert edit.body.sources[0].selector is not None
    assert edit.body.sources[0].selector.channel == 1
    assert edit.body.tracks[0].stream.channels == ['channel-0']


def test_mix_generates_route_gains_and_crossfade(tmp_path: Path) -> None:
    record_path = _record(tmp_path)
    recipe, _ = resolve_command('mix', tmp_path)

    edit = complete_or_generate(
        recipe,
        [record_path],
        EditOptions(route_gain=[0.75, 0.5], crossfade=0.25),
    )

    assert [r.gain for r in edit.body.routes] == [0.75, 0.5]
    assert len(edit.body.automation) == 2
    assert edit.body.automation[0].points[-1].frame == 12_000


def test_stitch_accepts_ordered_audio_files(tmp_path: Path) -> None:
    second = _audio(tmp_path / 'second.wav', channels=1)
    first = _audio(tmp_path / 'first.wav', channels=1)
    recipe, _ = resolve_command('stitch', tmp_path)

    edit = complete_or_generate(recipe, [second, first], EditOptions())

    assert [s.file for s in edit.body.sources] == [second.resolve(), first.resolve()]
    assert [c.timeline_start for c in edit.body.clips] == [0, 48_000]
    assert [d.path.as_posix() for d in edit.destinations] == ['audio/stitch.flac']


def test_split_expands_file_channels(tmp_path: Path) -> None:
    path = _audio(tmp_path / 'pair.wav', channels=2)
    recipe, _ = resolve_command('split', tmp_path)

    edit = complete_or_generate(recipe, [path], EditOptions())

    assert [s.channels for s in edit.body.sources] == [[0], [1]]
    assert [len(t.stream.channels) for t in edit.body.tracks] == [1, 1]


def test_split_preserves_explicit_mono_selection(tmp_path: Path) -> None:
    path = _audio(tmp_path / 'pair.wav', channels=2)
    recipe, _ = resolve_command('split', tmp_path)

    edit = complete_or_generate(recipe, [path], EditOptions(channel=['pair:2']))

    assert len(edit.body.sources) == 1
    assert edit.body.sources[0].channels == [1]


def test_media_directory_uses_lexical_order(tmp_path: Path) -> None:
    directory = tmp_path / 'takes'
    directory.mkdir()
    second = _audio(directory / 'b.wav', channels=1)
    first = _audio(directory / 'a.wav', channels=1)
    recipe, _ = resolve_command('clip', tmp_path)

    edit = complete_or_generate(recipe, [directory], EditOptions())

    assert [s.file for s in edit.body.sources] == [first.resolve(), second.resolve()]


def test_directory_with_multiple_sessions_is_rejected(tmp_path: Path) -> None:
    for name in ('one', 'two'):
        directory = tmp_path / name
        directory.mkdir()
        session_record.SessionRecordWriter(
            (directory / 'recording.toml').with_name('session-record.jsonl'),
            started_at='start',
        ).close()
        finalize_recording(directory / 'session-record.jsonl')
    recipe, _ = resolve_command('clip', tmp_path)

    with pytest.raises(RecsError, match='contains multiple session records'):
        complete_or_generate(recipe, [tmp_path], EditOptions())


def test_session_directories_use_qualified_selectors(tmp_path: Path) -> None:
    directories = [tmp_path / name for name in ('one', 'two')]
    records = []
    for directory in directories:
        directory.mkdir()
        records.append(_record(directory))
    recipe, _ = resolve_command('clip', tmp_path)

    edit = complete_or_generate(
        recipe,
        directories,
        EditOptions(channel=['two:device:pair']),
    )

    assert len(edit.body.sources) == 1
    assert edit.body.sources[0].record == records[1].resolve()
    assert edit.body.sources[0].selector is not None
    assert edit.body.sources[0].selector.track == 'pair'


def _record(directory: Path) -> Path:
    path = directory / 'recording.toml'
    writer = session_record.SessionRecordWriter(
        (path).with_name('session-record.jsonl'), started_at='start'
    )
    for source, track in [('device', 'pair'), ('room', 'pair')]:
        _audio(directory / f'{source}.wav', channels=2)
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
            session_record.AudioFileRecord(
                clock_id='audio',
                type='file_started',
                timestamp='start',
                frame_count=0,
                **values,
            )
        )
        writer.write(
            session_record.AudioFileRecord(
                clock_id='audio',
                type='file_finished',
                timestamp='end',
                frame_count=48_000,
                quantity_count=48_000,
                **values,
            )
        )
    writer.write(session_record.SessionFooter(ended_at='end', duration_seconds=1))
    writer.close()
    finalize_recording(writer.path)
    return path


def _audio(path: Path, channels: int) -> Path:
    soundfile.write(path, np.zeros((48_000, channels)), 48_000, subtype='FLOAT')
    return path
