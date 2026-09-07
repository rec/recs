from pathlib import Path
from time import monotonic_ns

import mido
import pytest

from recs.cfg.cfg import Cfg
from recs.midi import recorder
from recs.midi.recorder import MidiPacket, MidiRecorder
from recs.model.events import MidiEvent
from recs.ui.session_record import Record


class FakePort:
    def __init__(self, *messages: mido.Message, error: OSError | None = None) -> None:
        self.messages = list(messages)
        self.error = error
        self.closed = False

    def iter_pending(self) -> list[MidiPacket]:
        if self.error:
            raise self.error
        messages = self.messages
        self.messages = []
        return [MidiPacket(m, monotonic_ns()) for m in messages]

    def close(self) -> None:
        self.closed = True


def test_midi_recorder_records_pending_messages(tmp_path: Path) -> None:
    records: list[Record] = []
    warnings: list[str] = []
    port = FakePort(mido.Message('note_on', note=60, velocity=64, time=0.5))
    cfg = Cfg(output_directory=str(tmp_path))
    recorder = MidiRecorder(
        cfg,
        session_directory=tmp_path,
        warning=warnings.append,
        write_entry=records.append,
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
    assert records[1].type == 'file_started'
    assert records[2].type == 'file_finished'
    assert records[2].media_type == 'midi'
    assert records[2].quantity_count == 1
    assert records[2].source == 'Launchkey'
    saved = MidiEvent.model_validate_json(Path(records[2].path).read_text())
    assert saved.data == [144, 60, 64]


def test_midi_recorder_writes_messages_received_during_card_replacement(
    tmp_path: Path,
) -> None:
    records: list[Record] = []
    port = FakePort()
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path)),
        session_directory=tmp_path / 'old',
        warning=lambda warning: None,
        write_entry=records.append,
        input_names=lambda: ['Launchkey'],
        open_input=lambda name: port,
        timestamp=lambda: 12.0,
    )

    recorder.start()
    recorder.suspend_for_card_replace()
    port.messages.append(mido.Message('note_on', note=60, velocity=64))
    recorder.poll()
    recorder.open_session(tmp_path / 'new')
    recorder.close_session()

    path = next((tmp_path / 'new').glob('*.jsonl'))
    saved = MidiEvent.model_validate_json(path.read_text())
    assert saved.data == [144, 60, 64]


def test_midi_recorder_ignores_missing_backend_without_selected_input(
    tmp_path: Path,
) -> None:
    records: list[Record] = []
    warnings: list[str] = []

    def input_names() -> list[str]:
        raise ModuleNotFoundError('rtmidi')

    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path)),
        session_directory=tmp_path,
        warning=warnings.append,
        write_entry=records.append,
        input_names=input_names,
    )

    recorder.start()

    assert warnings == []
    assert records == []


def test_midi_recorder_does_not_discover_inputs_in_calibration_mode(
    tmp_path: Path,
) -> None:
    input_queries: list[bool] = []
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), calibrate=True),
        session_directory=tmp_path,
        warning=lambda warning: None,
        write_entry=lambda record: None,
        input_names=lambda: input_queries.append(True) or ['Launchkey'],
    )

    recorder.start()
    recorder.poll()

    assert input_queries == []
    assert not tmp_path.joinpath('Launchkey.mid').exists()


def test_midi_recorder_waits_for_selected_input(tmp_path: Path) -> None:
    records: list[Record] = []
    warnings: list[str] = []
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=warnings.append,
        write_entry=records.append,
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
    records: list[Record] = []
    warnings: list[str] = []
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path)),
        session_directory=tmp_path,
        warning=warnings.append,
        write_entry=records.append,
        input_names=lambda: ['Launchkey'],
        open_input=lambda name: FakePort(error=OSError('lost input')),
        timestamp=lambda: 12.0,
    )

    recorder.start()
    recorder.poll()
    recorder.stop()

    assert warnings == ['MIDI input Launchkey failed: lost input']
    assert records[0].type == 'midi_source_started'
    assert records[1].type == 'file_started'
    assert records[2].type == 'file_finished'
    assert records[3].type == 'clock_observation'
    assert records[4].type == 'midi_source_failed'
    assert records[4].source == 'Launchkey'
    assert records[4].value == 'lost input'


def test_midi_recorder_reopens_a_reconnected_port(tmp_path: Path) -> None:
    records: list[Record] = []
    warnings: list[str] = []
    names: list[str] = []
    clock = [0.0]
    first = FakePort(mido.Message('note_on', note=60, velocity=64))
    ports = [first, FakePort(mido.Message('note_off', note=60, velocity=64))]
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=warnings.append,
        write_entry=records.append,
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
        'file_started',
        'file_finished',
        'clock_observation',
        'midi_source_failed',
        'midi_source_started',
        'file_started',
        'file_finished',
        'clock_observation',
    ]
    paths = [path.name for path in tmp_path.glob('*.jsonl')]
    assert len(paths) == 2
    assert any(path.endswith('-2.jsonl') for path in paths)


def test_midi_recorder_stops_a_port_missing_from_discovery(tmp_path: Path) -> None:
    records: list[Record] = []
    names = ['Launchkey']
    clock = [0.0]
    port = FakePort()
    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=lambda message: None,
        write_entry=records.append,
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
        'file_started',
        'file_finished',
        'clock_observation',
        'midi_source_stopped',
    ]
    assert records[-1].reason == 'disconnected'
    assert recorder.status()[0]['state'] == 'waiting'


def test_midi_recorder_discovers_inputs_at_a_bounded_interval(tmp_path: Path) -> None:
    records: list[Record] = []
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
        write_entry=records.append,
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
    assert [record.type for record in records] == [
        'midi_source_started',
        'file_started',
    ]


def test_midi_recorder_rate_limits_unavailable_backend_warnings(tmp_path: Path) -> None:
    warnings: list[str] = []
    clock = [0.0]

    def input_names() -> list[str]:
        raise ModuleNotFoundError('rtmidi')

    recorder = MidiRecorder(
        Cfg(output_directory=str(tmp_path), midi_include=['Launchkey']),
        session_directory=tmp_path,
        warning=warnings.append,
        write_entry=lambda record: None,
        input_names=input_names,
        monotonic_clock=lambda: clock[0],
    )

    recorder.start()
    recorder.poll()
    clock[0] = 10.0
    recorder.poll()

    assert len(warnings) == 2


def test_callback_timestamps_survive_queue_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick = [1000]
    monkeypatch.setattr(recorder, 'monotonic_ns', lambda: tick[0])
    monkeypatch.setattr(mido, 'open_input', lambda name, callback: FakePort())
    port = recorder.CallbackPort('keys')
    port.capture(mido.Message('note_on', note=60))
    tick[0] = 1250
    port.capture(mido.Message('note_off', note=60))
    tick[0] = 999999
    packets = port.iter_pending()
    assert [p.received_tick for p in packets] == [1000, 1250]
    assert [p.message.bytes() for p in packets] == [[144, 60, 64], [128, 60, 64]]
    assert port.iter_pending() == []
    port.close()


@pytest.mark.parametrize('stop', [False, True])
def test_session_close_saves_queued_midi(tmp_path: Path, stop: bool) -> None:
    records: list[Record] = []
    port = FakePort(mido.Message('note_off', note=60))
    capture = MidiRecorder(
        Cfg(output_directory=str(tmp_path)),
        session_directory=tmp_path,
        warning=lambda message: None,
        write_entry=records.append,
        input_names=lambda: ['keys'],
        open_input=lambda name: port,
    )
    capture.start()
    if stop:
        capture.stop()
    else:
        capture.close_session()
    finished = next(r for r in records if r.type == 'file_finished')
    assert finished.quantity_count == 1
    event = MidiEvent.model_validate_json(Path(finished.path).read_text())
    assert event.data == [128, 60, 64]
    if not stop:
        capture.stop()
