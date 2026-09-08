import pytest
from ufor.events import ControlChange, Trigger

from recs.recsam.instrument import Instrument, SampleInstrument


@pytest.mark.parametrize('name', ['Pressure', '1-pressure', 'pressure.value'])
def test_control_declarations_use_the_shared_event_identifier_rules(name: str) -> None:
    with pytest.raises(ValueError):
        Instrument.model_validate({'name': 'Pads', 'controls': {name: {}}})


@pytest.mark.parametrize(
    ('control', 'value', 'valid'),
    [
        ('pressure', 0.0, True),
        ('pressure', 0.123456789, True),
        ('pressure', -0.1, False),
        ('bend', -1.0, True),
        ('bend', 1.0, True),
        ('missing', 0.0, False),
    ],
)
def test_events_use_the_instruments_declared_control_domains(
    control: str, value: float, valid: bool
) -> None:
    instrument = SampleInstrument.model_validate(
        {
            'format_version': 1,
            'instrument': {
                'name': 'Pads',
                'controls': {
                    'pressure': {},
                    'bend': {'polarity': 'bipolar'},
                },
            },
            'slots': [
                {
                    'id': 'pad',
                    'sample': 'pad.flac',
                    'mapping': {
                        'lowest_key': -10,
                        'highest_key': 1000,
                        'pitch_tracking': False,
                    },
                }
            ],
        }
    )
    trigger = Trigger(
        tick=0,
        ordinal=0,
        part='pads',
        trigger_id='hit',
        key=-1,
        controls={control: value},
    )
    change = ControlChange(
        tick=1, ordinal=1, control=control, value=value, scope='part', part='pads'
    )
    for event in (trigger, change):
        if valid:
            instrument.validate_event(event)
        else:
            with pytest.raises(ValueError):
                instrument.validate_event(event)
