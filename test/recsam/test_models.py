from pathlib import Path

import pytest
import tomlkit
from pydantic import TypeAdapter, ValidationError
from pytest_regressions.data_regression import DataRegressionFixture

from recs.recsam import modulation, playback, processing, selection
from recs.recsam.base import Model
from recs.recsam.controls import Control
from recs.recsam.instrument import Instrument, SampleInstrument


def test_documented_example(data_regression: DataRegressionFixture) -> None:
    spec = Path('doc/sample-format.md').read_text()
    example = spec.split('```toml\n', 1)[1].split('```', 1)[0]
    instrument = SampleInstrument.model_validate(tomlkit.parse(example))
    data_regression.check(instrument.model_dump(mode='json', exclude_unset=True))


@pytest.mark.parametrize(
    'heading',
    [
        'Named Articulations',
        'Release And Sustain Samples',
        'Named Controls And Live Modulation',
        'Pitch Bend And Pressure',
    ],
)
def test_documented_control_examples(heading: str) -> None:
    spec = Path('doc/sample-format.md').read_text()
    section = spec.split(f'# {heading}\n', 1)[1]
    example = tomlkit.parse(section.split('```toml\n', 1)[1].split('```', 1)[0])
    raw = document(instrument=example.get('instrument', {}))
    if 'slots' in example:
        raw['slots'] = example['slots']
    SampleInstrument.model_validate(raw)


def test_defaults_and_inheritance_roundtrip() -> None:
    raw = document(
        slot={
            'envelope': {'attack_seconds': 0.0},
        },
        instrument={'envelope': {'attack_seconds': 0.5, 'release_seconds': 0.2}},
    )
    instrument = SampleInstrument.model_validate(raw)
    slot = instrument.slots[0]
    assert slot.envelope.model_fields_set == {'attack_seconds'}
    assert slot.playback.model_fields_set == set()
    assert slot.playback.end_frame is None
    assert instrument.instrument.controls == {}
    assert instrument.instrument.sustain is None
    assert slot.mapping.minimum_velocity == 0.0
    assert slot.mapping.maximum_velocity == 1.0
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
        {'input': 'key'},
        {'input': 'velocity'},
        {'input': 'control', 'control': 'expression', 'scope': 'instrument'},
        {'input': 'control', 'control': 'pressure', 'scope': 'part'},
        {'input': 'control', 'control': 'pressure', 'scope': 'trigger'},
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
        {'input': 'key'},
        {'input': 'velocity'},
        {'input': 'control', 'control': 'expression'},
        {'input': 'control', 'control': 'pressure', 'scope': 'instrument'},
        {'input': 'control', 'control': 'pressure', 'scope': 'trigger'},
    ],
)
def test_each_crossfade_input_roundtrips(input_settings: dict[str, object]) -> None:
    raw = {'start': 0, 'end': 1, 'direction': 'in', **input_settings}
    adapter = TypeAdapter(modulation.LayerCrossfade)
    fade = adapter.validate_python(raw)
    assert adapter.validate_json(fade.model_dump_json()) == fade
    assert fade.model_dump(mode='json', exclude_unset=True) == raw


@pytest.mark.parametrize(
    'changes',
    [
        {'input': 'key', 'control': 1},
        {'input': 'key', 'scope': 'part'},
        {'input': 'key', 'smoothing_seconds': 0.1},
        {'input': 'key', 'source': 'lfo'},
        {'input': 'control'},
        {'input': 'control', 'control': True},
        {'input': 'control', 'control': 'pressure', 'scope': 'channel'},
        {'input': 'control', 'control': 'pressure', 'scope': 'voice'},
        {'input': 'envelope'},
        {'input': 'lfo', 'source': 'vibrato', 'scope': 'instrument'},
        {'input': 'lfo', 'source': 'vibrato', 'smoothing_seconds': 0.0},
        {'input': 'velocity', 'points': [{'input': -0.01, 'amount': 0}]},
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
            'input': 'control',
            'control': 'pressure',
        },
    ],
)
def test_invalid_modulations_are_rejected(changes: dict[str, object]) -> None:
    raw = {
        'input': 'key',
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
        {'input': 'velocity', 'start': -0.1, 'end': 1},
        {'input': 'key', 'start': 0.5},
        {'input': 'key', 'start': 100, 'end': 10},
        {'input': 'key', 'scope': 'part'},
        {'input': 'control'},
        {'input': 'control', 'control': 'pressure', 'scope': 'voice'},
    ],
)
def test_invalid_crossfades_are_rejected(changes: dict[str, object]) -> None:
    raw = {'input': 'key', 'start': 0, 'end': 127, 'direction': 'out', **changes}
    with pytest.raises(ValidationError):
        TypeAdapter(modulation.LayerCrossfade).validate_python(raw)


@pytest.mark.parametrize(
    ('model', 'raw'),
    [
        (
            playback.Mapping,
            {'lowest_key': 64, 'highest_key': 60, 'reference_pitch_hz': 60},
        ),
        (playback.Mapping, {'lowest_key': 0, 'highest_key': 128}),
        (
            playback.Mapping,
            {'lowest_key': True, 'highest_key': 128, 'pitch_tracking': False},
        ),
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
        (Control, {'default': -0.1}),
        (Control, {'default': float('inf')}),
        (Control, {'polarity': 'bipolar', 'default': -1.01}),
        (
            processing.EqualizerBand,
            {'id': 'tone', 'frequency_hz': 100, 'gain_db': 0, 'resonance': 0},
        ),
        (selection.Choke, {'group': 'hats', 'mode': 'fade'}),
        (selection.Choke, {'group': 'hats', 'mode': 'release', 'fade_seconds': 0.1}),
        (selection.Sustain, {'control': 'sustain', 'threshold': 0}),
        (selection.Articulations, {'ids': ['a', 'a'], 'default': 'a'}),
        (selection.Articulations, {'ids': ['a'], 'default': 'b'}),
        (Instrument, {'name': 'keys', 'tags': ['same', 'same']}),
        (Instrument, {'name': 'keys', 'controls': {'expression': {'default': 1.1}}}),
        (Instrument, {'name': 'keys', 'sustain': {'control': 'missing'}}),
        (
            Instrument,
            {
                'name': 'keys',
                'controls': {'sustain': {'polarity': 'bipolar'}},
                'sustain': {'control': 'sustain'},
            },
        ),
    ],
)
def test_invalid_settings_are_rejected(
    model: type[Model], raw: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(raw)


def test_articulation_bindings_have_unique_keys_and_disjoint_ranges() -> None:
    key = {'key': 24, 'articulation': 'a'}
    control = {
        'control': 'style',
        'minimum_value': 0,
        'maximum_value': 0.5,
        'articulation': 'a',
    }
    raw = {'ids': ['a'], 'default': 'a', 'keys': [key], 'controls': [control]}
    selection.Articulations.model_validate(raw)
    with pytest.raises(ValidationError, match='keyswitch'):
        selection.Articulations.model_validate({**raw, 'keys': [key, key]})
    with pytest.raises(ValidationError, match='Overlapping'):
        selection.Articulations.model_validate(
            {
                **raw,
                'controls': [
                    control,
                    {**control, 'minimum_value': 0.5, 'maximum_value': 1},
                ],
            }
        )
    selection.Articulations.model_validate(
        {
            **raw,
            'controls': [
                control,
                {**control, 'minimum_value': 0.6, 'maximum_value': 1},
            ],
        }
    )


@pytest.mark.parametrize('input', ['key', 'velocity'])
def test_static_curves_accept_unrestricted_keys_and_normalized_velocity(
    input: str,
) -> None:
    points = [-200, 10000] if input == 'key' else [0.0, 0.5000001, 1.0]
    curve = TypeAdapter(modulation.ModulationCurve).validate_python(
        {
            'input': input,
            'target': 'volume_db',
            'operation': 'add',
            'points': [{'input': p, 'amount': 0.0} for p in points],
        }
    )
    assert [p.input for p in curve.points] == points


@pytest.mark.parametrize(
    'settings',
    [
        {
            'modulation': [
                {
                    'input': 'control',
                    'control': 'expression',
                    'target': 'volume_db',
                    'operation': 'add',
                    'points': [{'input': -0.1, 'amount': 0.0}],
                }
            ]
        },
        {
            'crossfades': [
                {
                    'input': 'control',
                    'control': 'expression',
                    'direction': 'in',
                    'start': -0.1,
                    'end': 1.0,
                }
            ]
        },
    ],
)
def test_live_curves_validate_names_and_declared_polarity(
    settings: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match='Unknown control'):
        SampleInstrument.model_validate(document(slot=settings))
    with pytest.raises(ValidationError, match='must be in'):
        SampleInstrument.model_validate(
            document(
                slot=settings,
                instrument={'controls': {'expression': {}}},
            )
        )
    SampleInstrument.model_validate(
        document(
            slot=settings,
            instrument={'controls': {'expression': {'polarity': 'bipolar'}}},
        )
    )


def test_articulation_ranges_use_declared_control_domains() -> None:
    raw = {
        'name': 'Pads',
        'controls': {'style': {}},
        'articulations': {
            'ids': ['soft'],
            'default': 'soft',
            'controls': [
                {
                    'control': 'style',
                    'minimum_value': -1.0,
                    'maximum_value': 0.0,
                    'articulation': 'soft',
                }
            ],
        },
    }
    with pytest.raises(ValidationError, match='must be in'):
        Instrument.model_validate(raw)
    Instrument.model_validate({**raw, 'controls': {'style': {'polarity': 'bipolar'}}})


def test_pitch_tracking_uses_a_reference_frequency_not_selection_key() -> None:
    mapping = playback.Mapping(
        lowest_key=-200, highest_key=10000, reference_pitch_hz=443.123456
    )
    assert mapping.reference_pitch_hz == 443.123456
    with pytest.raises(ValidationError, match='reference_pitch_hz'):
        playback.Mapping(lowest_key=0, highest_key=127)
    assert (
        playback.Mapping(
            lowest_key=0, highest_key=127, pitch_tracking=False
        ).reference_pitch_hz
        is None
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
        {'trigger': 'logical_release'},
        {'lfos': [{'id': 'vibrato', 'frequency_hz': 5, 'scope': 'instrument'}]},
        {'crossfades': [{'input': 'key', 'direction': 'in', 'start': 0, 'end': 127}]},
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


def test_release_and_sustain_slots_can_inherit_one_shot() -> None:
    for trigger in ('release', 'logical_release'):
        SampleInstrument.model_validate(
            document(
                slot={'trigger': trigger}, instrument={'playback': {'mode': 'one_shot'}}
            )
        )
    mapping = {
        'lowest_key': 60,
        'highest_key': 60,
        'event_key': 60,
        'pitch_tracking': False,
    }
    for trigger in ('sustain_press', 'sustain_release'):
        SampleInstrument.model_validate(
            document(
                slot={'trigger': trigger, 'mapping': mapping},
                instrument={
                    'playback': {'mode': 'one_shot'},
                    'controls': {'sustain': {}},
                    'sustain': {'control': 'sustain'},
                },
            )
        )
    with pytest.raises(ValidationError, match='require a sustain control'):
        SampleInstrument.model_validate(
            document(
                slot={'trigger': 'sustain_press', 'mapping': mapping},
                instrument={
                    'playback': {'mode': 'one_shot'},
                },
            )
        )


@pytest.mark.parametrize(
    ('trigger', 'mapping'),
    [
        ('sustain_press', {'pitch_tracking': False}),
        ('sustain_press', {'pitch_tracking': False, 'event_key': 100}),
        ('sustain_release', {'reference_pitch_hz': 440, 'event_key': 60}),
        ('start', {'pitch_tracking': False, 'event_key': 60}),
    ],
)
def test_sustain_event_keys_are_contained_untracked_and_not_ordinary_keys(
    trigger: str, mapping: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        SampleInstrument.model_validate(
            document(
                slot={
                    'trigger': trigger,
                    'mapping': {'lowest_key': 48, 'highest_key': 84, **mapping},
                },
                instrument={
                    'playback': {'mode': 'one_shot'},
                    'controls': {'sustain': {}},
                    'sustain': {'control': 'sustain'},
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
        'input': 'control',
        'control': 'expression',
        'target': 'volume_db',
        'operation': 'add',
        'points': [{'input': 0, 'amount': 0}],
    }
    with pytest.raises(ValidationError, match='Duplicate modulation'):
        SampleInstrument.model_validate(
            document(instrument={'modulation': [route, {**route, 'scope': 'part'}]})
        )


def test_named_sources_and_duration_targets_from_the_spec() -> None:
    spec = Path('doc/sample-format.md').read_text()
    section = spec.split('## Modulation Envelopes And LFOs', 1)[1]
    example = section.split('```toml\n', 1)[1].split('```', 1)[0]
    settings = dict(tomlkit.parse(example)['instrument'])
    settings['modulation'].append(
        {
            'target': 'envelopes.pitch-fall.decay_seconds',
            'input': 'key',
            'operation': 'multiply',
            'points': [{'input': 60, 'amount': 2.0}],
        }
    )
    instrument = SampleInstrument.model_validate(document(instrument=settings))
    assert instrument.instrument.envelopes[0].id == 'pitch-fall'
    assert instrument.instrument.lfos[0].frequency_hz == 5.0
    assert instrument.instrument.envelope.decay_seconds == 0.0


def test_cross_references_and_sustain_alternative_keys() -> None:
    raw = document(
        instrument={
            'selections': [{'id': 'takes', 'mode': 'cycle'}],
            'playback': {'mode': 'one_shot'},
            'controls': {'sustain': {}},
            'sustain': {'control': 'sustain'},
        },
        slot={
            'selection': 'takes',
            'choke_group': 'tails',
            'chokes': [{'group': 'tails', 'mode': 'immediate'}],
            'trigger': 'sustain_press',
            'mapping': {
                'lowest_key': 48,
                'highest_key': 84,
                'event_key': 60,
                'pitch_tracking': False,
            },
        },
    )
    instrument = SampleInstrument.model_validate(raw)
    second = instrument.slots[0].model_dump(exclude_unset=True)
    second['id'] = 'second'
    raw['slots'].append(second)
    SampleInstrument.model_validate(raw)
    second['mapping'] = {
        'lowest_key': 48,
        'highest_key': 84,
        'event_key': 61,
        'pitch_tracking': False,
    }
    with pytest.raises(ValidationError, match='share event_key'):
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
                'mapping': {
                    'lowest_key': 48,
                    'highest_key': 84,
                    'reference_pitch_hz': 60,
                },
                **(slot or {}),
            }
        ],
    }
