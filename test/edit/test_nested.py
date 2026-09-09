from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
import soundfile
from ufor.arrangement import ArrangementDocument
from ufor.codec import document_toml
from ufor.interface import Address, Definition, Direction, Node, Port

from recs.edit.commands import complete_or_generate
from recs.edit.graph import validate_graph
from recs.edit.nested import load_composition, resolve_sources
from recs.edit.options import EditOptions
from recs.edit.render import Renderer
from recs.edit.session import execute_edit


def test_nested_and_flat_recording_mixes_are_identical(tmp_path: Path) -> None:
    media = tmp_path / 'take.wav'
    samples = np.linspace(-0.5, 0.5, 96000, dtype=np.float32)
    soundfile.write(media, samples, 48000, subtype='FLOAT')
    child = complete_or_generate(
        {'_command': {'operation': 'clip'}},
        [media],
        EditOptions(format='wav', subtype='float'),
    )
    child_path = tmp_path / 'child.toml'
    # Generated references are relative to the authoring working directory.
    raw = child.model_dump()
    for n in raw['body']['nodes']:
        n['definition']['path'] = Path(n['definition']['path']).resolve().name
    child = ArrangementDocument.model_validate(raw)
    child_path.write_text(document_toml(child))
    outer_raw = child.model_dump()
    outer_raw['body']['nodes'] = [
        {'id': 'first', 'definition': {'path': 'child.toml'}},
        {'id': 'second', 'definition': {'path': 'child.toml'}},
    ]
    original = outer_raw['body']['clips'][0]
    outer_raw['body']['clips'] = [
        dict(
            original,
            id=n,
            source={'node': n, 'port': child.ports[0].id},
            source_start=48000,
            source_end=96000,
            timeline_start=0,
            gain=0.5,
        )
        for n in ('first', 'second')
    ]
    outer = ArrangementDocument.model_validate(outer_raw)
    sources = resolve_sources(outer, tmp_path)
    result = Renderer(outer, sources, validate_graph(outer, sources)).outputs[
        outer.ports[0].id
    ]
    expected = samples[48000:, None]
    soundfile.write(tmp_path / 'nested.wav', result.samples, 48000, subtype='FLOAT')
    soundfile.write(tmp_path / 'flat.wav', expected, 48000, subtype='FLOAT')
    assert (tmp_path / 'nested.wav').read_bytes() == (
        tmp_path / 'flat.wav'
    ).read_bytes()
    # Reading disjoint windows and joining them preserves the same native history.
    halves = []
    for start in (0, 24000):
        request = outer.model_dump()
        request['ports'][0]['binding'].update(start=start, end=start + 24000)
        block = ArrangementDocument.model_validate(request)
        block_sources = resolve_sources(block, tmp_path)
        block_output = Renderer(
            block, block_sources, validate_graph(block, block_sources)
        ).outputs
        halves.append(block_output[outer.ports[0].id].samples)
    np.testing.assert_array_equal(np.concatenate(halves), expected)
    assert (
        sources[Address(node='first', port=child.ports[0].id)]
        is not sources[Address(node='second', port=child.ports[0].id)]
    )
    destination = tmp_path / 'rendered'
    execute_edit(outer, tmp_path, destination)
    saved, rate = soundfile.read(
        destination / outer.destinations[0].path, always_2d=True
    )
    assert rate == 48000
    np.testing.assert_array_equal(saved, expected)


def test_forwarded_output_and_package_boundaries(tmp_path: Path) -> None:
    media = tmp_path / 'take.wav'
    soundfile.write(media, np.zeros(48000, dtype=np.float32), 48000, subtype='FLOAT')
    child = complete_or_generate(
        {'_command': {'operation': 'clip'}}, [media], EditOptions()
    )
    definition = Path(child.body.nodes[0].definition.path).resolve()
    outer = ArrangementDocument(
        id='forward',
        name='Forward',
        timebases=child.timebases,
        ports=[
            Port(
                id='main',
                direction=Direction.output,
                stream=child.ports[0].stream,
                binding=Address(node='recording', port='audio'),
            )
        ],
        body={
            'timebase': 'audio',
            'nodes': [
                Node(id='recording', definition=Definition(path=definition.name))
            ],
        },
    )
    sources = resolve_sources(outer, tmp_path)
    rendered = Renderer(outer, sources, validate_graph(outer, sources)).outputs['main']
    soundfile.write(tmp_path / 'forward.wav', rendered.samples, 48000, subtype='FLOAT')
    assert len(rendered.samples) == 48000
    package = tmp_path / 'package'
    package.mkdir()
    outside = outer.model_copy(
        update={
            'body': outer.body.model_copy(
                update={
                    'nodes': [
                        Node(
                            id='recording',
                            definition=Definition(path='../' + definition.name),
                        )
                    ]
                }
            )
        }
    )
    with pytest.raises(ValueError, match='escapes package root'):
        load_composition(outside, package, package)
    (package / definition.name).symlink_to(definition)
    with pytest.raises(ValueError, match='escapes package root'):
        load_composition(outer, package, package)
    pinned = outer.model_dump()
    pinned['body']['nodes'][0]['definition']['sha256'] = sha256(
        definition.read_bytes()
    ).hexdigest()
    pinned_edit = ArrangementDocument.model_validate(pinned)
    load_composition(pinned_edit, tmp_path)
    definition.write_text(definition.read_text() + '\n')
    with pytest.raises(ValueError, match='digest mismatch'):
        load_composition(pinned_edit, tmp_path)


def test_instrument_realization_is_reported_as_unsupported(tmp_path: Path) -> None:
    from ufor.sequence import SequenceDocument

    from recs.recsam.sfz import read

    soundfile.write(tmp_path / 'sample.wav', np.zeros(48000, dtype=np.float32), 48000)
    path = tmp_path / 'piano.sfz'
    path.write_text('<region> sample=sample.wav key=69')
    instrument = read(path).instrument
    assert instrument is not None
    (tmp_path / 'piano.toml').write_text(document_toml(instrument))
    audio = next(p.stream for p in instrument.ports if p.direction == Direction.output)
    notes = SequenceDocument.model_validate(
        {
            'id': 'notes',
            'name': 'Notes',
            'timebases': [{'id': 'output', 'rate': {'numerator': 48000}}],
            'ports': [
                {
                    'id': 'events',
                    'direction': 'output',
                    'stream': {
                        'family': 'event',
                        'timebase': 'output',
                        'kinds': ['trigger'],
                    },
                    'binding': {'sequence': True},
                }
            ],
            'body': {'timebase': 'output', 'start': 0, 'end': 48000, 'events': []},
        }
    )
    (tmp_path / 'notes.toml').write_text(document_toml(notes))
    edit = ArrangementDocument.model_validate(
        {
            'id': 'mix',
            'name': 'Mix',
            'timebases': notes.timebases,
            'ports': [
                {
                    'id': 'main',
                    'direction': 'output',
                    'stream': audio,
                    'binding': {'track': 'mix'},
                }
            ],
            'body': {
                'timebase': 'output',
                'nodes': [
                    {'id': 'piano', 'definition': {'path': 'piano.toml'}},
                    {'id': 'notes', 'definition': {'path': 'notes.toml'}},
                ],
                'connections': [
                    {
                        'source': {'node': 'notes', 'port': 'events'},
                        'destination': {'node': 'piano', 'port': 'performance'},
                    }
                ],
                'tracks': [{'id': 'mix', 'stream': audio}],
                'clips': [
                    {
                        'id': 'piano',
                        'source': {'node': 'piano', 'port': 'audio'},
                        'track': 'mix',
                        'source_start': 0,
                        'source_end': 48000,
                        'timeline_start': 0,
                    }
                ],
            },
        }
    )
    with pytest.raises(
        ValueError, match='audio realization of instrument is unsupported'
    ):
        resolve_sources(edit, tmp_path)
