from pathlib import Path

import pytest
import tomlkit
from pydantic import TypeAdapter, ValidationError
from pytest_regressions.data_regression import DataRegressionFixture

from recs.recsam import modulation, playback, processing, selection
from recs.recsam.base import Model
from recs.recsam.instrument import Instrument, SampleInstrument


def test_documented_example(data_regression: DataRegressionFixture) -> None:
    spec = Path('doc/sample-format.md').read_text()
    example = spec.split('```toml\n', 1)[1].split('```', 1)[0]
    instrument = SampleInstrument.model_validate(tomlkit.parse(example))
    data_regression.check(instrument.model_dump(mode='json', exclude_unset=True))


def test_defaults_and_inheritance_roundtrip() -> None:
    raw = document(
        slot={
            'envelope': {'attack_seconds': 0.0},
            'pitch_bend': {'range_semitones': 0.0},
        },
        instrument={'envelope': {'attack_seconds': 0.5, 'release_seconds': 0.2}},
    )
    instrument = SampleInstrument.model_validate(raw)
    slot = instrument.slots[0]
    assert slot.envelope.model_fields_set == {'attack_seconds'}
    assert slot.pitch_bend.model_fields_set == {'range_semitones'}
    assert slot.playback.model_fields_set == set()
    assert slot.playback.end_frame is None
    assert instrument.instrument.pitch_bend.range_semitones == 2.0
    assert instrument.instrument.sustain.controller == 64
    assert instrument.model_dump(mode='json', exclude_unset=True) == raw
    restored = SampleInstrument.model_validate(tomlkit.parse(tomlkit.dumps(raw)))
    assert restored.model_dump(exclude_unset=True) == raw


def test_models_are_frozen_and_list_defaults_are_independent() -> None:
    first = Instrument(name='first')
    second = Instrument(name='second')
    with pytest.raises(ValidationError, match='frozen'):
        first.name = 'changed'
    first.tags.append('local')
    assert second.tags == []
    first.processing.equalizer.append(
        processing.EqualizerBand(id='tone', frequency_hz=100, gain_db=0, resonance=1)
    )
    assert second.processing.equalizer == []
    assert Instrument(name='third').processing.equalizer == []


@pytest.mark.parametrize(
    'input_settings',
    [
        {'input': 'note'},
        {'input': 'velocity'},
        {'input': 'controller', 'controller': 11, 'scope': 'instrument'},
        {'input': 'channel_pressure'},
        {'input': 'note_pressure'},
        {'input': 'envelope', 'source': 'pitch'},
        {'input': 'lfo', 'source': 'vibrato'},
    ],
)
def test_each_modulation_input_roundtrips(input_settings: dict[str, object]) -> None:
    raw = {
        'target': 'volume_db',
        'operation': 'add',
        'points': [{'input': 1, 'amount': -3.0}],
        **input_settings,
    }
    adapter = TypeAdapter(modulation.ModulationCurve)
    curve = adapter.validate_python(raw)
    assert adapter.validate_json(curve.model_dump_json()) == curve
    assert curve.model_dump(mode='json', exclude_unset=True) == raw


@pytest.mark.parametrize(
    'input_settings',
    [
        {'input': 'note'},
        {'input': 'velocity'},
        {'input': 'controller', 'controller': 1},
        {'input': 'channel_pressure', 'scope': 'instrument'},
        {'input': 'note_pressure'},
    ],
)
def test_each_crossfade_input_roundtrips(input_settings: dict[str, object]) -> None:
    raw = {'start': 1, 'end': 127, 'direction': 'in', **input_settings}
    adapter = TypeAdapter(modulation.LayerCrossfade)
    fade = adapter.validate_python(raw)
    assert adapter.validate_json(fade.model_dump_json()) == fade
    assert fade.model_dump(mode='json', exclude_unset=True) == raw


@pytest.mark.parametrize(
    'changes',
    [
        {'input': 'note', 'controller': 1},
        {'input': 'note', 'scope': 'channel'},
        {'input': 'note', 'smoothing_seconds': 0.1},
        {'input': 'note', 'source': 'lfo'},
        {'input': 'controller'},
        {'input': 'controller', 'controller': True},
        {'input': 'note_pressure', 'scope': 'channel'},
        {'input': 'channel_pressure', 'scope': 'voice'},
        {'input': 'envelope'},
        {'input': 'lfo', 'source': 'vibrato', 'scope': 'instrument'},
        {'input': 'lfo', 'source': 'vibrato', 'smoothing_seconds': 0.0},
        {'input': 'velocity', 'points': [{'input': 0, 'amount': 0}]},
        {'points': [{'input': 60.5, 'amount': 0}]},
        {'points': [{'input': True, 'amount': 0}]},
        {'points': [{'input': 1, 'amount': float('nan')}]},
        {'points': [{'input': 2, 'amount': 0}, {'input': 1, 'amount': 0}]},
        {'points': [{'input': 1, 'amount': 0}, {'input': 1, 'amount': 1}]},
        {'points': []},
        {'target': 'volume_db', 'operation': 'multiply'},
        {'target': 'equalizer.band.quality_factor', 'operation': 'multiply'},
        {'target': 'equalizer.band.resonance', 'operation': 'multiply'},
        {'target': 'lfos.vibrato.frequency_hz'},
        {'target': 'envelope.sustain_level'},
        {
            'target': 'envelope.attack_seconds',
            'operation': 'multiply',
            'input': 'channel_pressure',
        },
    ],
)
def test_invalid_modulations_are_rejected(changes: dict[str, object]) -> None:
    raw = {
        'input': 'note',
        'target': 'volume_db',
        'operation': 'add',
        'points': [{'input': 1, 'amount': 0}],
        **changes,
    }
    with pytest.raises(ValidationError):
        TypeAdapter(modulation.ModulationCurve).validate_python(raw)


@pytest.mark.parametrize(
    'changes',
    [
        {'input': 'lfo', 'source': 'vibrato'},
        {'input': 'velocity', 'start': 0},
        {'input': 'note', 'start': 0.5},
        {'input': 'note', 'start': 100, 'end': 10},
        {'input': 'note', 'scope': 'channel'},
        {'input': 'controller'},
        {'input': 'note_pressure', 'scope': 'instrument'},
    ],
)
def test_invalid_crossfades_are_rejected(changes: dict[str, object]) -> None:
    raw = {'input': 'note', 'start': 0, 'end': 127, 'direction': 'out', **changes}
    with pytest.raises(ValidationError):
        TypeAdapter(modulation.LayerCrossfade).validate_python(raw)


@pytest.mark.parametrize(
    ('model', 'raw'),
    [
        (playback.Mapping, {'lowest_note': 64, 'highest_note': 60, 'root_note': 60}),
        (playback.Mapping, {'lowest_note': 0, 'highest_note': 128, 'root_note': 60}),
        (playback.Loop, {'start_frame': 0, 'end_frame': 1}),
        (playback.Loop, {'start_frame': 0, 'end_frame': 10, 'crossfade_frames': 1}),
        (playback.Loop, {'start_frame': 0, 'end_frame': 10, 'crossfade_frames': 5}),
        (playback.SlotPlayback, {'start_frame': 20, 'end_frame': 10}),
        (
            playback.SlotPlayback,
            {'start_frame': 10, 'loop': {'start_frame': 0, 'end_frame': 20}},
        ),
        (playback.Envelope, {'attack_seconds': -0.1}),
        (playback.Envelope, {'sustain_level': 1.1}),
        (playback.Envelope, {'hold_seconds': True}),
        (playback.Envelope, {'release_seconds': '0.5'}),
        (playback.LFO, {'id': 'vibrato', 'frequency_hz': 0}),
        (playback.LFO, {'id': 'vibrato', 'frequency_hz': 5, 'phase_cycles': 1}),
        (playback.PitchBend, {'range_semitones': -1}),
        (playback.PitchBend, {'smoothing_seconds': float('inf')}),
        (
            processing.EqualizerBand,
            {'id': 'tone', 'frequency_hz': 100, 'gain_db': 0, 'resonance': 0},
        ),
        (selection.Choke, {'group': 'hats', 'mode': 'fade'}),
        (selection.Choke, {'group': 'hats', 'mode': 'release', 'fade_seconds': 0.1}),
        (selection.Sustain, {'threshold': 0}),
        (selection.Articulations, {'ids': ['a', 'a'], 'default': 'a'}),
        (selection.Articulations, {'ids': ['a'], 'default': 'b'}),
        (Instrument, {'name': 'keys', 'tags': ['same', 'same']}),
        (Instrument, {'name': 'keys', 'controller_defaults': {'01': 127}}),
        (Instrument, {'name': 'keys', 'controller_defaults': {'128': 127}}),
        (Instrument, {'name': 'keys', 'controller_defaults': {'1': 128}}),
    ],
)
def test_invalid_settings_are_rejected(
    model: type[Model], raw: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(raw)


def test_articulation_bindings_have_unique_keys_and_disjoint_ranges() -> None:
    key = {'note': 24, 'articulation': 'a'}
    control = {
        'controller': 1,
        'minimum_value': 0,
        'maximum_value': 63,
        'articulation': 'a',
    }
    raw = {'ids': ['a'], 'default': 'a', 'keys': [key], 'controllers': [control]}
    selection.Articulations.model_validate(raw)
    with pytest.raises(ValidationError, match='keyswitch'):
        selection.Articulations.model_validate({**raw, 'keys': [key, key]})
    with pytest.raises(ValidationError, match='Overlapping'):
        selection.Articulations.model_validate(
            {
                **raw,
                'controllers': [
                    control,
                    {**control, 'minimum_value': 63, 'maximum_value': 127},
                ],
            }
        )
    selection.Articulations.model_validate(
        {
            **raw,
            'controllers': [
                control,
                {**control, 'minimum_value': 64, 'maximum_value': 127},
            ],
        }
    )


@pytest.mark.parametrize(
    'path',
    [
        '/audio/a.wav',
        '../a.wav',
        'a/../../b.wav',
        'https://host/a.wav',
        'C:/a.wav',
        '.',
    ],
)
def test_sample_references_cannot_escape_lexically(path: str) -> None:
    with pytest.raises(ValidationError, match='sample'):
        SampleInstrument.model_validate(document(slot={'sample': path}))


def test_paths_and_unicode_metadata_are_preserved() -> None:
    raw = document(
        slot={'sample': 'audio/../audio/take.wav', 'tags': ['étude', 'two words']}
    )
    result = SampleInstrument.model_validate(raw)
    assert result.slots[0].sample == 'audio/../audio/take.wav'
    assert result.slots[0].tags[0] == 'étude'
    assert result.instrument.tags == []


@pytest.mark.parametrize(
    'slot',
    [
        {'selection': 'missing'},
        {'articulations': ['missing']},
        {'chokes': [{'group': 'missing', 'mode': 'release'}]},
        {'trigger': 'note_release'},
        {'lfos': [{'id': 'vibrato', 'frequency_hz': 5, 'scope': 'instrument'}]},
        {'crossfades': [{'input': 'note', 'direction': 'in', 'start': 0, 'end': 127}]},
    ],
)
def test_invalid_slot_relationships_are_rejected(slot: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SampleInstrument.model_validate(document(slot=slot))


def test_inherited_playback_controls_loop_validation() -> None:
    loop = {'start_frame': 0, 'end_frame': 100, 'crossfade_frames': 10}
    with pytest.raises(ValidationError, match='mirror'):
        SampleInstrument.model_validate(
            document(
                slot={'playback': {'loop': loop}},
                instrument={'playback': {'direction': 'mirror'}},
            )
        )
    with pytest.raises(ValidationError, match='while_held'):
        SampleInstrument.model_validate(
            document(
                slot={'playback': {'loop': loop}},
                instrument={'playback': {'mode': 'one_shot'}},
            )
        )
    SampleInstrument.model_validate(
        document(
            slot={
                'playback': {'direction': 'forward', 'mode': 'while_held', 'loop': loop}
            },
            instrument={'playback': {'direction': 'mirror', 'mode': 'one_shot'}},
        )
    )


def test_release_and_pedal_slots_can_inherit_one_shot() -> None:
    for trigger in ('key_release', 'note_release', 'pedal_press', 'pedal_release'):
        SampleInstrument.model_validate(
            document(
                slot={'trigger': trigger}, instrument={'playback': {'mode': 'one_shot'}}
            )
        )
    with pytest.raises(ValidationError, match='sustain enabled'):
        SampleInstrument.model_validate(
            document(
                slot={'trigger': 'pedal_press'},
                instrument={
                    'playback': {'mode': 'one_shot'},
                    'sustain': {'enabled': False},
                },
            )
        )


def test_modulation_references_are_local_and_source_kinds_must_match() -> None:
    source = {'id': 'pitch', 'attack_seconds': 0.1}
    route = {
        'input': 'envelope',
        'source': 'pitch',
        'target': 'tuning_cents',
        'operation': 'add',
        'points': [{'input': 1.0, 'amount': 100}],
    }
    SampleInstrument.model_validate(
        document(instrument={'envelopes': [source], 'modulation': [route]})
    )
    with pytest.raises(ValidationError, match='Unknown local'):
        SampleInstrument.model_validate(
            document(slot={'modulation': [route]}, instrument={'envelopes': [source]})
        )
    with pytest.raises(ValidationError, match='Unknown local lfo'):
        SampleInstrument.model_validate(
            document(
                instrument={
                    'envelopes': [source],
                    'modulation': [{**route, 'input': 'lfo'}],
                }
            )
        )
    with pytest.raises(ValidationError, match='Duplicate source'):
        SampleInstrument.model_validate(
            document(
                instrument={
                    'envelopes': [source],
                    'lfos': [{'id': 'pitch', 'frequency_hz': 5}],
                }
            )
        )


def test_duplicate_curves_normalize_implicit_scope() -> None:
    route = {
        'input': 'controller',
        'controller': 1,
        'target': 'volume_db',
        'operation': 'add',
        'points': [{'input': 0, 'amount': 0}],
    }
    with pytest.raises(ValidationError, match='Duplicate modulation'):
        SampleInstrument.model_validate(
            document(instrument={'modulation': [route, {**route, 'scope': 'channel'}]})
        )


def test_named_sources_and_duration_targets_from_the_spec() -> None:
    spec = Path('doc/sample-format.md').read_text()
    section = spec.split('## Modulation Envelopes And LFOs', 1)[1]
    example = section.split('```toml\n', 1)[1].split('```', 1)[0]
    settings = dict(tomlkit.parse(example)['instrument'])
    settings['modulation'].append(
        {
            'target': 'envelopes.pitch-fall.decay_seconds',
            'input': 'note',
            'operation': 'multiply',
            'points': [{'input': 60, 'amount': 2.0}],
        }
    )
    instrument = SampleInstrument.model_validate(document(instrument=settings))
    assert instrument.instrument.envelopes[0].id == 'pitch-fall'
    assert instrument.instrument.lfos[0].frequency_hz == 5.0
    assert instrument.instrument.envelope.decay_seconds == 0.0


def test_cross_references_and_pedal_alternative_roots() -> None:
    raw = document(
        instrument={
            'selections': [{'id': 'takes', 'mode': 'cycle'}],
            'playback': {'mode': 'one_shot'},
        },
        slot={
            'selection': 'takes',
            'choke_group': 'tails',
            'chokes': [{'group': 'tails', 'mode': 'immediate'}],
            'trigger': 'pedal_press',
        },
    )
    instrument = SampleInstrument.model_validate(raw)
    second = instrument.slots[0].model_dump(exclude_unset=True)
    second['id'] = 'second'
    raw['slots'].append(second)
    SampleInstrument.model_validate(raw)
    second['mapping'] = {'lowest_note': 48, 'highest_note': 84, 'root_note': 61}
    with pytest.raises(ValidationError, match='share root_note'):
        SampleInstrument.model_validate(raw)
    second['id'] = 'glass'
    with pytest.raises(ValidationError, match='Duplicate slot ID'):
        SampleInstrument.model_validate(raw)


def test_spatial_bounds_include_both_scopes_and_modulation() -> None:
    with pytest.raises(ValidationError, match='combined pan range'):
        SampleInstrument.model_validate(
            document(
                instrument={'processing': {'pan': 0.6}},
                slot={'processing': {'pan': 0.5}},
            )
        )
    route = {
        'input': 'lfo',
        'source': 'motion',
        'target': 'pan',
        'operation': 'add',
        'points': [{'input': -1.0, 'amount': -0.5}, {'input': 1.0, 'amount': 0.5}],
    }
    settings = {'lfos': [{'id': 'motion', 'frequency_hz': 1.0}], 'modulation': [route]}
    SampleInstrument.model_validate(document(instrument=settings))
    with pytest.raises(ValidationError, match='combined pan range'):
        SampleInstrument.model_validate(
            document(instrument=settings, slot={'processing': {'pan': 0.8}})
        )


def test_delayed_lfo_neutral_amount_is_validated() -> None:
    settings = {
        'processing': {'pan': 0.8},
        'lfos': [{'id': 'motion', 'frequency_hz': 1.0, 'delay_seconds': 0.5}],
        'modulation': [
            {
                'input': 'lfo',
                'source': 'motion',
                'target': 'pan',
                'operation': 'add',
                'points': [{'input': 0.0, 'amount': -0.5}],
            }
        ],
    }
    with pytest.raises(ValidationError, match='combined pan range'):
        SampleInstrument.model_validate(
            document(instrument=settings, slot={'processing': {'pan': 0.4}})
        )


@pytest.mark.parametrize('version', [True, 1.0, '1', 2])
def test_only_integer_format_version_one_is_accepted(version: object) -> None:
    with pytest.raises(ValidationError):
        SampleInstrument.model_validate({**document(), 'format_version': version})


def test_unknown_fields_and_old_bank_key_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SampleInstrument.model_validate({**document(), 'bank': {}})
    with pytest.raises(ValidationError):
        SampleInstrument.model_validate(document(slot={'playback': {'typo': 1}}))


def document(
    slot: dict[str, object] | None = None, instrument: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        'format_version': 1,
        'instrument': {'name': 'Glass', **(instrument or {})},
        'slots': [
            {
                'id': 'glass',
                'sample': 'audio/glass.wav',
                'mapping': {'lowest_note': 48, 'highest_note': 84, 'root_note': 60},
                **(slot or {}),
            }
        ],
    }
