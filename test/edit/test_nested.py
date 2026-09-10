from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
import soundfile
from ufor.arrangement import ArrangementScore
from ufor.codec import score_toml
from ufor.interface import Output, OutputSelection, Part, ScoreVersion

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
    for n in raw['body']['parts']:
        n['score']['path'] = Path(n['score']['path']).resolve().name
    child = ArrangementScore.model_validate(raw)
    child_path.write_text(score_toml(child))
    outer_raw = child.model_dump()
    outer_raw['body']['parts'] = [
        {'name': 'first', 'score': {'path': 'child.toml'}},
        {'name': 'second', 'score': {'path': 'child.toml'}},
    ]
    original = outer_raw['body']['clips'][0]
    outer_raw['body']['clips'] = [
        dict(
            original,
            name=n,
            source={'name': n, 'output': child.outputs[0].name},
            source_start=48000,
            source_end=96000,
            timeline_start=0,
            gain=0.5,
        )
        for n in ('first', 'second')
    ]
    outer = ArrangementScore.model_validate(outer_raw)
    sources = resolve_sources(outer, tmp_path)
    result = Renderer(outer, sources, validate_graph(outer, sources)).outputs[
        outer.outputs[0].name
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
        request['outputs'][0]['binding'].update(start=start, end=start + 24000)
        block = ArrangementScore.model_validate(request)
        block_sources = resolve_sources(block, tmp_path)
        block_output = Renderer(
            block, block_sources, validate_graph(block, block_sources)
        ).outputs
        halves.append(block_output[outer.outputs[0].name].samples)
    np.testing.assert_array_equal(np.concatenate(halves), expected)
    assert (
        sources[OutputSelection(name='first', output=child.outputs[0].name)]
        is not sources[OutputSelection(name='second', output=child.outputs[0].name)]
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
    score = Path(child.body.parts[0].score.path).resolve()
    outer = ArrangementScore(
        name='forward',
        title='Forward',
        timebases=child.timebases,
        outputs=[
            Output(
                name='main',
                stream=child.outputs[0].stream,
                binding=OutputSelection(name='recording', output='audio'),
            )
        ],
        body={
            'timebase': 'audio',
            'parts': [Part(name='recording', score=ScoreVersion(path=score.name))],
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
                    'parts': [
                        Part(
                            name='recording',
                            score=ScoreVersion(path='../' + score.name),
                        )
                    ]
                }
            )
        }
    )
    with pytest.raises(ValueError, match='escapes package root'):
        load_composition(outside, package, package)
    (package / score.name).symlink_to(score)
    with pytest.raises(ValueError, match='escapes package root'):
        load_composition(outer, package, package)
    pinned = outer.model_dump()
    pinned['body']['parts'][0]['score']['sha256'] = sha256(
        score.read_bytes()
    ).hexdigest()
    pinned_edit = ArrangementScore.model_validate(pinned)
    load_composition(pinned_edit, tmp_path)
    score.write_text(score.read_text() + '\n')
    with pytest.raises(ValueError, match='digest mismatch'):
        load_composition(pinned_edit, tmp_path)


def test_instrument_realization_is_reported_as_unsupported(tmp_path: Path) -> None:
    from ufor.sequence import SequenceScore

    from recs.recsam.sfz import read

    soundfile.write(tmp_path / 'sample.wav', np.zeros(48000, dtype=np.float32), 48000)
    path = tmp_path / 'piano.sfz'
    path.write_text('<region> sample=sample.wav key=69')
    instrument = read(path).instrument
    assert instrument is not None
    (tmp_path / 'piano.toml').write_text(score_toml(instrument))
    audio = next(p.stream for p in instrument.outputs)
    notes = SequenceScore.model_validate(
        {
            'name': 'notes',
            'title': 'Notes',
            'timebases': [{'name': 'output', 'rate': {'numerator': 48000}}],
            'outputs': [
                {
                    'name': 'events',
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
    (tmp_path / 'notes.toml').write_text(score_toml(notes))
    edit = ArrangementScore.model_validate(
        {
            'name': 'mix',
            'title': 'Mix',
            'timebases': notes.timebases,
            'outputs': [{'name': 'main', 'stream': audio, 'binding': {'track': 'mix'}}],
            'body': {
                'timebase': 'output',
                'parts': [
                    {'name': 'piano', 'score': {'path': 'piano.toml'}},
                    {'name': 'notes', 'score': {'path': 'notes.toml'}},
                ],
                'connections': [
                    {
                        'source': {'name': 'notes', 'output': 'events'},
                        'destination': {'name': 'piano', 'input': 'performance'},
                    }
                ],
                'tracks': [{'name': 'mix', 'stream': audio}],
                'clips': [
                    {
                        'name': 'piano',
                        'source': {'name': 'piano', 'output': 'audio'},
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
