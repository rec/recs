from pathlib import Path

import mido

from recs.base.types import MidiTiming
from recs.midi.writer import TICKS_PER_BEAT, MidiWriter


def test_midi_writer_uses_960_ticks_per_beat(tmp_path: Path) -> None:
    writer = MidiWriter(tmp_path, 'Launchkey', MidiTiming.mido)

    writer.record(mido.Message('note_on', note=60, velocity=64, time=0.5))
    record = writer.finish()

    saved = mido.MidiFile(record.path)
    assert saved.ticks_per_beat == TICKS_PER_BEAT
    assert saved.tracks[0][2].time == 960
    assert record.kind == 'midi'
    assert record.message_count == 1
    assert record.timing_source == 'mido'


def test_midi_writer_can_use_system_timing(tmp_path: Path) -> None:
    writer = MidiWriter(tmp_path, 'Launchkey', MidiTiming.system)

    writer.record(mido.Message('note_on', note=60, velocity=64), timestamp=10.0)
    writer.record(mido.Message('note_off', note=60, velocity=0), timestamp=10.25)
    record = writer.finish()

    saved = mido.MidiFile(record.path)
    assert saved.tracks[0][2].time == 0
    assert saved.tracks[0][3].time == 480
    assert record.message_count == 2
