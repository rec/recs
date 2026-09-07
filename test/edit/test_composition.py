from pathlib import Path

import numpy as np
import pytest
import soundfile
from pydantic import ValidationError

from recs.base.errors import RecsError
from recs.edit import materialized
from recs.edit.composition import (
    CompositionEdit,
    canonical_composition,
    composition_summary,
    execute_composition,
    parse_composition,
    resolve_composition,
)
from recs.edit.materialized import MaterializedAudio
from recs.edit.record import ResolvedSource
from recs.ui import session_record


def test_composition_round_trips_and_allows_no_edits() -> None:
    value = parse_composition(
        'schema_version = 2\nkind = "composition"\nresult = "root"\n'
    )

    assert value.edits == []
    assert parse_composition(canonical_composition(value)) == value


@pytest.mark.parametrize(
    'text',
    [
        'schema_version = 1\nkind = "composition"\nresult = "root"\n',
        'schema_version = 2\nkind = "other"\nresult = "root"\n',
        'schema_version = 2\nkind = "composition"\nresult = "root"\nunknown = true\n',
        (
            'schema_version = 2\nkind = "composition"\nresult = "clip"\n'
            '[[edits]]\nid = "clip"\ncommand = "clip"\ninputs = ["root"]\n'
            'unknown = true\n'
        ),
    ],
)
def test_composition_rejects_unknown_schema_values(text: str) -> None:
    with pytest.raises(ValidationError):
        parse_composition(text)


@pytest.mark.parametrize(
    'body',
    [
        (
            'result = "missing"\n'
            '[[edits]]\nid = "one"\ncommand = "clip"\ninputs = ["root"]\n'
        ),
        (
            'result = "one"\n'
            '[[edits]]\nid = "one"\ncommand = "clip"\ninputs = ["root"]\n'
            '[[edits]]\nid = "one"\ncommand = "clip"\ninputs = ["root"]\n'
        ),
        (
            'result = "root"\n'
            '[[edits]]\nid = "root"\ncommand = "clip"\ninputs = ["root"]\n'
        ),
        (
            'result = "one"\n'
            '[[edits]]\nid = "one"\ncommand = "clip"\ninputs = ["missing"]\n'
        ),
        'result = "one"\n[[edits]]\nid = "one"\ncommand = "clip"\ninputs = ["one"]\n',
        (
            'result = "one"\n'
            '[[edits]]\nid = "one"\ncommand = "clip"\ninputs = ["two"]\n'
            '[[edits]]\nid = "two"\ncommand = "clip"\ninputs = ["one"]\n'
        ),
        (
            'result = "one"\n'
            '[[edits]]\nid = "one"\ncommand = "clip"\ninputs = ["root"]\n'
            '[[edits]]\nid = "unused"\ncommand = "clip"\ninputs = ["root"]\n'
        ),
    ],
)
def test_composition_rejects_invalid_graphs(body: str) -> None:
    with pytest.raises(ValidationError):
        parse_composition('schema_version = 2\nkind = "composition"\n' + body)


def test_empty_composition_returns_input_without_creating_output(
    tmp_path: Path,
) -> None:
    record_path, _ = _record(tmp_path)
    value = CompositionEdit(schema_version=2, kind='composition', result='root')

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
            ('clip', 'root:device:voice'),
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
    assert all(e.resolved is not None for e in canonical.edits)
    assert canonical.edits[0].resolved is not None
    assert canonical.edits[1].resolved is not None
    first_output = canonical.edits[0].resolved.edit['outputs'][0]
    assert 'path' not in first_output
    assert 'format' not in first_output
    assert 'subtype' not in first_output
    assert canonical.edits[1].resolved.edit['outputs'][0]['format'] == 'wav'

    rendered, rate = soundfile.read(
        destination / 'audio/node-1-root-device-voice.wav',
        dtype='float32',
        always_2d=True,
    )
    np.testing.assert_array_equal(rendered, audio)
    assert rate == 48_000
    final_record = session_record.read(result)
    assert final_record.files[-1].source == 'edit'
    assert final_record.files[-1].track_name == 'node-1-root-device-voice'


def test_composition_resolves_every_command_before_creating_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, _ = _record(tmp_path)
    complete = tmp_path / 'complete.toml'
    complete.write_text('schema_version = 1\nsample_rate = 48000\n')
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(
        'schema_version = 2\n'
        'kind = "composition"\n'
        'result = "complete"\n'
        '[[edits]]\n'
        'id = "clip"\n'
        'command = "clip"\n'
        'inputs = ["root"]\n'
        'channel = ["root:device:voice"]\n'
        '[[edits]]\n'
        'id = "complete"\n'
        'command = "complete.toml"\n'
        'inputs = ["clip"]\n'
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
            ('clip', 'root:device:voice'),
            ('clip', 'node-1:missing'),
            ('clip', 'node-2:never'),
        )
    )
    value = parse_composition(composition_path.read_text())
    destination = tmp_path / 'composed'

    def materialize_source(source: ResolvedSource) -> MaterializedAudio:
        pytest.fail(f'preflight decoded {source.selector}')

    monkeypatch.setattr(materialized, 'materialize_source', materialize_source)

    with pytest.raises(RecsError, match='Unknown channel selectors'):
        execute_composition(value, composition_path, record_path, destination)

    assert not destination.exists()


def test_composition_summary_resolves_stages_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, _ = _record(tmp_path)
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(_composition_text(('clip', 'root:device:voice')))
    destination = tmp_path / 'composed'

    summary = composition_summary(
        parse_composition(composition_path.read_text()),
        composition_path,
        record_path,
        destination,
    )

    assert f'Record: {record_path.resolve()}' in summary
    assert 'node-1: clip' in summary
    assert 'Inputs: root' in summary
    assert 'Selectors: root:device:voice' in summary
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
        'schema_version = 2\n'
        'kind = "composition"\n'
        'result = "second"\n'
        '[[edits]]\n'
        'id = "first"\n'
        'command = "clip"\n'
        'inputs = ["root"]\n'
        'format = "wav"\n'
        '[[edits]]\n'
        'id = "second"\n'
        'command = "clip"\n'
        'inputs = ["first"]\n'
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
        _composition_text(('clip', 'root:device:voice'), ('clip', None))
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
        second / 'audio/node-1-root-device-voice.wav',
        dtype='float32',
        always_2d=True,
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
        'schema_version = 2\n'
        'kind = "composition"\n'
        'result = "derived"\n'
        '[[edits]]\n'
        'id = "derived"\n'
        'command = "derived"\n'
        'inputs = ["root"]\n'
    )

    resolved = resolve_composition(value, tmp_path)

    assert resolved[0].recipe == {'_command': {'operation': 'clip', 'help': 'derived'}}


def test_composition_mixes_parallel_edit_branches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    record_path, audio = _record(tmp_path)
    original_materialize = materialized.materialize_source
    materialized_sources: list[str] = []

    def materialize_source(source: ResolvedSource) -> MaterializedAudio:
        materialized_sources.append(source.selector)
        return original_materialize(source)

    monkeypatch.setattr(materialized, 'materialize_source', materialize_source)
    composition_path = tmp_path / 'compose.toml'
    composition_path.write_text(
        'schema_version = 2\n'
        'kind = "composition"\n'
        'result = "master"\n'
        '[[edits]]\n'
        'id = "quiet"\n'
        'command = "clip"\n'
        'inputs = ["root"]\n'
        'channel = ["root:device:voice"]\n'
        'gain = 0.25\n'
        '[[edits]]\n'
        'id = "loud"\n'
        'command = "clip"\n'
        'inputs = ["root"]\n'
        'channel = ["root:device:voice"]\n'
        'gain = 0.5\n'
        '[[edits]]\n'
        'id = "master"\n'
        'command = "mix"\n'
        'inputs = ["quiet", "loud"]\n'
        'channel = ["quiet:*", "loud:*"]\n'
        'format = "wav"\n'
        'subtype = "float"\n'
    )
    destination = tmp_path / 'composed'

    execute_composition(
        parse_composition(composition_path.read_text()),
        composition_path,
        record_path,
        destination,
    )

    rendered, rate = soundfile.read(
        destination / 'audio/mix.wav', dtype='float32', always_2d=True
    )
    assert rate == 48_000
    np.testing.assert_allclose(rendered[:, 0], audio[:, 0] * 0.75, atol=1e-7)
    assert materialized_sources == ['device:voice']
    canonical = parse_composition((destination / 'edit.toml').read_text())
    assert [e.id for e in canonical.edits] == ['loud', 'quiet', 'master']
    assert canonical.edits[-1].inputs == ['quiet', 'loud']


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
    result = 'root' if not steps else f'node-{len(steps)}'
    text = f'schema_version = 2\nkind = "composition"\nresult = "{result}"\n'
    for index, (command, channel) in enumerate(steps):
        node_id = f'node-{index + 1}'
        input_id = 'root' if index == 0 else f'node-{index}'
        text += (
            f'[[edits]]\nid = "{node_id}"\ncommand = "{command}"\n'
            f'inputs = ["{input_id}"]\n'
        )
        if channel is not None:
            text += f'channel = ["{channel}"]\n'
        if index == len(steps) - 1:
            text += 'format = "wav"\nsubtype = "float"\n'
    return text
