from pathlib import Path

import mido
from pytest_regressions.data_regression import DataRegressionFixture

from recs.base.types import MidiTiming
from recs.midi.writer import MidiClock, MidiWriter
from recs.model.events import MidiEvent


def test_native_midi_preserves_sub_smf_tick_timing(
    tmp_path: Path, data_regression: DataRegressionFixture
) -> None:
    clock = MidiClock(MidiTiming.mido, 0)
    writer = MidiWriter(tmp_path, 'Launchkey', MidiTiming.mido, 1_725_000_000, clock)
    for delta in (0.0001, 0.0001, 0.0001):
        writer.record(mido.Message('note_on', note=60, velocity=64, time=delta))
    record = writer.finish()
    saved = [
        MidiEvent.model_validate_json(s)
        for s in Path(record.path).read_text().splitlines()
    ]
    data_regression.check([s.model_dump() for s in saved])
    assert record.quantity_count == 3
    assert record.start_tick == 0
    assert record.end_tick == 300001
    assert record.format == 'recs_events'


def test_system_clock_retains_first_event_offset_and_equal_tick_order(
    tmp_path: Path,
) -> None:
    writer = MidiWriter(
        tmp_path,
        'Launchkey',
        MidiTiming.system,
        1_725_000_000,
        MidiClock(MidiTiming.system, 1000),
    )
    writer.record(mido.Message('note_on', note=60), received_tick=1250)
    writer.record(mido.Message('note_off', note=60), received_tick=1250)
    record = writer.finish()
    saved = [
        MidiEvent.model_validate_json(s)
        for s in Path(record.path).read_text().splitlines()
    ]
    assert [(s.tick, s.ordinal) for s in saved] == [(1250, 0), (1250, 1)]
    assert record.start_tick == 1000
    assert record.end_tick == 1251
