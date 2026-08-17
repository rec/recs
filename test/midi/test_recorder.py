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
            'open': True,
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


def test_midi_recorder_warns_when_selected_input_is_missing(tmp_path: Path) -> None:
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

    assert warnings == ['No selected MIDI inputs detected']
    assert records == []


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
    assert records[1].type == 'midi_source_failed'
    assert records[1].source == 'Launchkey'
    assert records[1].value == 'lost input'
