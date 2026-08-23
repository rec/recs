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
            'selector': 'Launchkey',
            'port_name': 'Launchkey',
            'state': 'recording',
            'failed': False,
            'message_count': 1,
            'last_message_timestamp': 12.0,
            'last_failure': None,
            'last_failure_timestamp': None,
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
            'selector': 'Launchkey',
            'port_name': None,
            'state': 'waiting',
            'failed': False,
            'message_count': 0,
            'last_message_timestamp': None,
            'last_failure': None,
            'last_failure_timestamp': None,
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
    clock = [0.0]
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
        monotonic_clock=lambda: clock[0],
    )

    recorder.start()
    assert recorder.status()[0]['state'] == 'waiting'

    names.append('Launchkey')
    clock[0] = 10.0
    recorder.poll()
    first.error = OSError('disconnected')
    recorder.poll()
    assert recorder.status()[0]['state'] == 'failed'

    clock[0] = 20.0
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
    paths = [path.name for path in tmp_path.glob('*.mid')]
    assert len(paths) == 2
    assert any(path.endswith('-2.mid') for path in paths)


def test_midi_recorder_stops_a_port_missing_from_discovery(tmp_path: Path) -> None:
    records: list[ManifestRecord] = []
    names = ['Launchkey']
    clock = [0.0]
    port = FakePort()
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=lambda message: None,
        write_record=records.append,
        input_names=lambda: names,
        open_input=lambda name: port,
        monotonic_clock=lambda: clock[0],
    )

    recorder.start()
    names.clear()
    clock[0] = 10.0
    recorder.poll()

    assert port.closed
    assert [record.type for record in records] == [
        'midi_source_started',
        'file_finished',
        'midi_source_stopped',
    ]
    assert records[-1].reason == 'disconnected'
    assert recorder.status()[0]['state'] == 'waiting'


def test_midi_recorder_discovers_inputs_at_a_bounded_interval(tmp_path: Path) -> None:
    records: list[ManifestRecord] = []
    clock = [0.0]
    names: list[str] = []
    calls = 0

    def input_names() -> list[str]:
        nonlocal calls
        calls += 1
        return names

    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=lambda message: None,
        write_record=records.append,
        input_names=input_names,
        open_input=lambda name: FakePort(),
        monotonic_clock=lambda: clock[0],
    )

    recorder.start()
    names.append('Launchkey')
    recorder.poll()
    clock[0] = 10.0
    recorder.poll()

    assert calls == 2
    assert [record.type for record in records] == ['midi_source_started']


def test_midi_recorder_rate_limits_unavailable_backend_warnings(tmp_path: Path) -> None:
    warnings: list[str] = []
    clock = [0.0]

    def input_names() -> list[str]:
        raise ModuleNotFoundError('rtmidi')

    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=warnings.append,
        write_record=lambda record: None,
        input_names=input_names,
        monotonic_clock=lambda: clock[0],
    )

    recorder.start()
    recorder.poll()
    clock[0] = 10.0
    recorder.poll()

    assert len(warnings) == 2
