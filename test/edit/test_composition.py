from pathlib import Path

import numpy as np
import pytest
import soundfile
from pydantic import ValidationError

from recs.base.errors import RecsError
from recs.edit.composition import (
    CompositionEdit,
    canonical_composition,
    composition_summary,
    execute_composition,
    parse_composition,
    resolve_composition,
)
from recs.ui import session_record


def test_composition_round_trips_and_allows_no_edits() -> None:
    value = parse_composition('schema_version = 1\nkind = "composition"\n')

    assert value.edits == []
    assert parse_composition(canonical_composition(value)) == value


@pytest.mark.parametrize(
    'text',
    [
        'schema_version = 2\nkind = "composition"\n',
        'schema_version = 1\nkind = "other"\n',
        'schema_version = 1\nkind = "composition"\nunknown = true\n',
        (
            'schema_version = 1\nkind = "composition"\n'
            '[[edits]]\ncommand = "clip"\nunknown = true\n'
        ),
    ],
)
def test_composition_rejects_unknown_schema_values(text: str) -> None:
    with pytest.raises(ValidationError):
        parse_composition(text)


def test_empty_composition_returns_input_without_creating_output(
    tmp_path: Path,
) -> None:
    record_path, _ = _record(tmp_path)
    value = CompositionEdit(schema_version=1, kind='composition')

    assert execute_composition(value, tmp_path / 'compose.toml', record_path, None) == (
        record_path.resolve()
    )

    with pytest.raises(RecsError, match='does not create a destination'):
        execute_composition(
            value, tmp_path / 'compose.toml', record_path, tmp_path / 'output'
        )
    assert not (tmp_path / 'output').exists()


def test_composition_executes_each_edit_from_the_previous_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, audio = _record(tmp_path)
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(
        _composition_text(
            ('clip', 'device:voice'),
            ('clip', None),
        )
    )
    value = parse_composition(composition_path.read_text())
    destination = tmp_path / 'composed'

    result = execute_composition(value, composition_path, record_path, destination)

    assert result == destination / 'session-record.jsonl'
    assert not (destination / '001-clip').exists()
    assert not (destination / '002-clip').exists()
    assert not (destination / 'commands').exists()
    canonical = parse_composition((destination / 'edit.toml').read_text())
    assert [e.command for e in canonical.edits] == ['clip', 'clip']
    assert len(canonical.resolved_commands) == 2
    assert len(canonical.stages) == 2
    first_output = canonical.stages[0].edit['outputs'][0]
    assert 'path' not in first_output
    assert 'format' not in first_output
    assert 'subtype' not in first_output
    assert canonical.stages[1].edit['outputs'][0]['format'] == 'wav'

    rendered, rate = soundfile.read(
        destination / 'audio/edit-device-voice.wav',
        dtype='float32',
        always_2d=True,
    )
    np.testing.assert_array_equal(rendered, audio)
    assert rate == 48_000
    final_record = session_record.read(result)
    assert final_record.files[-1].source == 'edit'
    assert final_record.files[-1].track_name == 'edit-device-voice'


def test_composition_resolves_every_command_before_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, _ = _record(tmp_path)
    complete = tmp_path / 'complete.toml'
    complete.write_text('schema_version = 1\nsample_rate = 48000\n')
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(
        _composition_text(('clip', 'device:voice'))
        + '[[edits]]\ncommand = "complete.toml"\n'
    )
    value = parse_composition(composition_path.read_text())

    with pytest.raises(RecsError, match='complete arrangement'):
        execute_composition(value, composition_path, record_path, tmp_path / 'composed')
    assert not (tmp_path / 'composed').exists()


def test_composition_stops_after_a_child_cannot_read_the_previous_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, _ = _record(tmp_path)
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(
        _composition_text(
            ('clip', 'device:voice'),
            ('clip', 'edit:missing'),
            ('clip', 'edit:never'),
        )
    )
    value = parse_composition(composition_path.read_text())
    destination = tmp_path / 'composed'

    with pytest.raises(RecsError, match='Unknown channel selectors'):
        execute_composition(value, composition_path, record_path, destination)

    assert not destination.exists()


def test_composition_summary_resolves_stages_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, _ = _record(tmp_path)
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(_composition_text(('clip', 'device:voice')))
    destination = tmp_path / 'composed'

    summary = composition_summary(
        parse_composition(composition_path.read_text()),
        composition_path,
        record_path,
        destination,
    )

    assert f'Record: {record_path.resolve()}' in summary
    assert '1: clip' in summary
    assert 'Selectors: device:voice' in summary
    assert 'Intermediate media: memory only' in summary
    assert 'Materialized audio: 192000 bytes' in summary
    assert 'Estimated peak materialized audio:' in summary
    assert f'Result: {destination / "session-record.jsonl"}' in summary
    assert not destination.exists()


def test_composition_rejects_explicit_intermediate_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, _ = _record(tmp_path)
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(
        'schema_version = 1\n'
        'kind = "composition"\n'
        '[[edits]]\n'
        'command = "clip"\n'
        'format = "wav"\n'
        '[[edits]]\n'
        'command = "clip"\n'
    )
    destination = tmp_path / 'composed'

    with pytest.raises(RecsError, match='intermediate encoding'):
        execute_composition(
            parse_composition(composition_path.read_text()),
            composition_path,
            record_path,
            destination,
        )

    assert not destination.exists()


def test_canonical_composition_runs_without_command_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, audio = _record(tmp_path)
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(
        _composition_text(('clip', 'device:voice'), ('clip', None))
    )
    first = tmp_path / 'first'
    execute_composition(
        parse_composition(composition_path.read_text()),
        composition_path,
        record_path,
        first,
    )
    canonical_path = first / 'edit.toml'
    second = tmp_path / 'second'
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'missing-config'))

    result = execute_composition(
        parse_composition(canonical_path.read_text()),
        canonical_path,
        record_path,
        second,
    )

    rendered, rate = soundfile.read(
        second / 'audio/edit-device-voice.wav', dtype='float32', always_2d=True
    )
    assert result == second / 'session-record.jsonl'
    assert rate == 48_000
    np.testing.assert_array_equal(rendered, audio)


def test_resolved_composition_flattens_inherited_recipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    commands = tmp_path / '.recs/edit'
    commands.mkdir(parents=True)
    (commands / 'base.toml').write_text(
        '[_command]\noperation = "clip"\nhelp = "base"\n'
    )
    (commands / 'derived.toml').write_text(
        'extends = "base"\n[_command]\nhelp = "derived"\n'
    )
    value = parse_composition(
        'schema_version = 1\nkind = "composition"\n' '[[edits]]\ncommand = "derived"\n'
    )

    resolved = resolve_composition(value, tmp_path)

    assert resolved[0].recipe == {'_command': {'operation': 'clip', 'help': 'derived'}}


def _record(directory: Path) -> tuple[Path, np.ndarray]:
    source = directory / 'source'
    source.mkdir()
    audio = np.linspace(-0.5, 0.5, 48_000, dtype=np.float32)[:, np.newaxis]
    soundfile.write(source / 'voice.wav', audio, 48_000, subtype='FLOAT')
    record_path = source / 'session-record.jsonl'
    writer = session_record.SessionRecordWriter(
        record_path, started_at='start', session_id='input'
    )
    values = {
        'media_type': 'audio',
        'stream_id': 'audio:device:voice',
        'format': 'wav',
        'path': 'voice.wav',
        'source': 'device',
        'track_name': 'voice',
        'source_channels': [1],
        'channels': 1,
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
    writer.write(session_record.SessionFooter(ended_at='end', duration_seconds=1))
    writer.close()
    return record_path, audio


def _composition_text(*steps: tuple[str, str | None]) -> str:
    text = 'schema_version = 1\nkind = "composition"\n'
    for index, (command, channel) in enumerate(steps):
        text += f'[[edits]]\ncommand = "{command}"\n'
        if channel is not None:
            text += f'channel = ["{channel}"]\n'
        if index == len(steps) - 1:
            text += 'format = "wav"\nsubtype = "float"\n'
    return text
