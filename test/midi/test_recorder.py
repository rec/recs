from pathlib import Path

import mido

from recs.cfg.cfg import Cfg
from recs.midi.recorder import MidiRecorder
from recs.ui.session_manifest import ManifestRecord


class FakePort:
    def __init__(self, *messages: mido.Message, error: OSError | None = None) -> None:
        self.messages = list(messages)
        self.error = error
        self.closed = False

    def iter_pending(self) -> list[mido.Message]:
        if self.error:
            raise self.error
        messages = self.messages
        self.messages = []
        return messages

    def close(self) -> None:
        self.closed = True


def test_midi_recorder_records_pending_messages(tmp_path: Path) -> None:
    records: list[ManifestRecord] = []
    warnings: list[str] = []
    port = FakePort(mido.Message('note_on', note=60, velocity=64, time=0.5))
    cfg = Cfg(output_directory=str(tmp_path))
    recorder = MidiRecorder(
        cfg,
        session_directory=tmp_path,
        warning=warnings.append,
        write_record=records.append,
        input_names=lambda: ['Launchkey'],
        open_input=lambda name: port,
        timestamp=lambda: 12.0,
    )

    recorder.start()
    recorder.poll()
    assert recorder.status() == [
        {
            'name': 'Launchkey',
            'state': 'recording',
            'failed': False,
            'message_count': 1,
            'last_message_timestamp': 12.0,
        }
    ]
    recorder.stop()

    assert warnings == []
    assert port.closed
    assert records[0].type == 'midi_source_started'
    assert records[0].source == 'Launchkey'
    assert records[1].type == 'file_finished'
    assert records[1].kind == 'midi'
    assert records[1].message_count == 1
    assert records[1].midi_port == 'Launchkey'
    saved = mido.MidiFile(records[1].path)
    assert saved.tracks[0][2].type == 'note_on'


def test_midi_recorder_ignores_missing_backend_without_selected_input(
    tmp_path: Path,
) -> None:
    records: list[ManifestRecord] = []
    warnings: list[str] = []

    def input_names() -> list[str]:
        raise ModuleNotFoundError('rtmidi')

    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path)),
        session_directory=tmp_path,
        warning=warnings.append,
        write_record=records.append,
        input_names=input_names,
    )

    recorder.start()

    assert warnings == []
    assert records == []


def test_midi_recorder_waits_for_selected_input(tmp_path: Path) -> None:
    records: list[ManifestRecord] = []
    warnings: list[str] = []
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=warnings.append,
        write_record=records.append,
        input_names=lambda: [],
    )

    recorder.start()

    assert warnings == []
    assert records == []
    assert recorder.status() == [
        {
            'name': 'Launchkey',
            'state': 'waiting',
            'failed': False,
            'message_count': 0,
            'last_message_timestamp': None,
        }
    ]


def test_midi_recorder_records_port_failure(tmp_path: Path) -> None:
    records: list[ManifestRecord] = []
    warnings: list[str] = []
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path)),
        session_directory=tmp_path,
        warning=warnings.append,
        write_record=records.append,
        input_names=lambda: ['Launchkey'],
        open_input=lambda name: FakePort(error=OSError('lost input')),
        timestamp=lambda: 12.0,
    )

    recorder.start()
    recorder.poll()
    recorder.stop()

    assert warnings == ['MIDI input Launchkey failed: lost input']
    assert records[0].type == 'midi_source_started'
    assert records[1].type == 'file_finished'
    assert records[2].type == 'midi_source_failed'
    assert records[2].source == 'Launchkey'
    assert records[2].value == 'lost input'


def test_midi_recorder_reopens_a_reconnected_port(tmp_path: Path) -> None:
    records: list[ManifestRecord] = []
    warnings: list[str] = []
    names: list[str] = []
    first = FakePort(mido.Message('note_on', note=60, velocity=64))
    ports = [first, FakePort(mido.Message('note_off', note=60, velocity=64))]
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=warnings.append,
        write_record=records.append,
        input_names=lambda: names,
        open_input=lambda name: ports.pop(0),
        timestamp=lambda: 12.0,
    )

    recorder.start()
    assert recorder.status()[0]['state'] == 'waiting'

    names.append('Launchkey')
    recorder.poll()
    first.error = OSError('disconnected')
    recorder.poll()
    assert recorder.status()[0]['state'] == 'waiting'

    recorder.poll()
    recorder.stop()

    assert warnings == ['MIDI input Launchkey failed: disconnected']
    assert [record.type for record in records] == [
        'midi_source_started',
        'file_finished',
        'midi_source_failed',
        'midi_source_started',
        'file_finished',
    ]
    assert len(list(tmp_path.glob('*.mid'))) == 2
