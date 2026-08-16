from recs.cfg.cfg import Cfg
from recs.midi import device


def test_selected_inputs_defaults_to_all_sorted() -> None:
    assert device.selected_inputs(Cfg(), ['B', 'A']) == ['A', 'B']


def test_selected_inputs_applies_prefix_filters() -> None:
    cfg = Cfg(midi_include=['Launch'], midi_exclude=['Launch Bad'])

    assert device.selected_inputs(cfg, ['Other', 'Launch Good', 'Launch Bad']) == [
        'Launch Good'
    ]
