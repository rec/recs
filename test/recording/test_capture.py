import base64
from pathlib import Path

import mido
import numpy as np
import pytest
import soundfile
from pydantic import TypeAdapter
from ufor.encoding import Format
from ufor.events import MidiEvent, OscEvent, StoredEvent
from ufor.recording import AudioStream, EventStream, GapReason
from ufor.references import RecordSelector

from recs.audio.block import Block
from recs.audio.channel_writer import ChannelWriter
from recs.base.errors import RecsError
from recs.base.types import MidiTiming
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.time_settings import TimeSettings
from recs.cfg.track import Track
from recs.edit.inputs import SourceSpec
from recs.edit.materialized import materialize_source
from recs.edit.record import resolve_input
from recs.midi.export import export_midi
from recs.midi.recorder import MidiPacket, MidiRecorder
from recs.osc import recorder
from recs.osc.config import Node
from recs.recording.files import verify_recording
from recs.recording.finalize import prepare_recording
from recs.recording.read import read_recording, read_recording_chain
from recs.ui import session_record
from recs.ui.recording_session import RecordingSession
from recs.ui.session_explain import explain
from recs.ui.session_export import export
from recs.ui.source_recorder import SourceFileEvents


class MidiPort:
    def __init__(self) -> None:
        self.messages: list[MidiPacket] = []

    def iter_pending(self) -> list[MidiPacket]:
        result, self.messages = self.messages, []
        return result

    def close(self) -> None:
        pass


class PacketQueue:
    def __init__(self) -> None:
        self.packets: list[bytes] = []

    def recvfrom(self, size: int) -> tuple[bytes, tuple[str, int]]:
        if not self.packets:
            raise BlockingIOError
        return self.packets.pop(0), ('127.0.0.1', 9000)


def test_mixed_capture_survives_rotation_volume_change_and_portable_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tick = [1_000_000_000]
    monkeypatch.setattr(recorder.time, 'monotonic_ns', lambda: tick[0])
    monkeypatch.setattr(recorder, 'MAX_FILE_BYTES', 1)
    original = tmp_path / 'original'
    first, second = original / 'a', original / 'b'
    session = RecordingSession('capture', 0.0)
    session.start(first / 'session-record.jsonl', enabled=True)
    port = MidiPort()
    midi = MidiRecorder(
        Cfg(midi_timing=MidiTiming.system),
        first / 'midi',
        lambda s: None,
        session.write,
        input_names=lambda: ['keys'],
        open_input=lambda n: port,
        capture_clock=lambda: tick[0],
    )
    midi.start()
    osc = recorder.OscNodeRecorder(
        Node(name='desk'), first / 'osc', lambda s: None, session.write, None
    )
    packets = PacketQueue()
    osc.socket = packets
    osc.open_output(first / 'osc')
    _audio(session, first, 0)
    for index in range(2):
        tick[0] += 100_000
        port.messages.append(
            MidiPacket(mido.Message('note_on', note=60 + index, velocity=64), tick[0])
        )
        packets.packets.append(b'undecodable-' + bytes([index]))
        midi.poll()
        osc.poll()
    midi.suspend_for_card_replace()
    osc.suspend_for_card_replace()
    session.write(
        session_record.EventRecord(
            type='session_continued_at',
            timestamp='switch',
            continued_at='../b/session-record.jsonl',
        )
    )
    session.finish(4.0)
    assert session.record_errors == []
    # Incoming events are stamped before buffering while the new volume is unavailable.
    tick[0] += 100_000
    port.messages.append(MidiPacket(mido.Message('note_off', note=60), tick[0]))
    packets.packets.append(b'buffered')
    midi.poll()
    osc.poll()
    session.reset(4.0, continued_from='../a/session-record.jsonl')
    session.start(second / 'session-record.jsonl', enabled=True)
    tick[0] += 100_000
    midi.open_session(second / 'midi')
    osc.open_session(second / 'osc')
    _audio(session, second, 192000)
    midi.close_session()
    osc.close_output()
    session.finish(8.0)
    assert session.record_errors == []
    destination = export(first / 'recording.toml', tmp_path / 'export')
    original.rename(tmp_path / 'moved-original')
    records = read_recording_chain(destination / 'recording.toml')
    stored: dict[str, list[StoredEvent]] = {'midi': [], 'osc': []}
    for path, document in records:
        verified = verify_recording(document, path.parent)
        assert verified.unresolved_audio_files == 0
        assert document.body.clock_observations
        assets = {a.id: a for a in document.assets}
        for stream in document.body.streams:
            if isinstance(stream, AudioStream):
                reasons = {g.reason for g in stream.gaps}
                assert GapReason.silence_suppressed in reasons
                assert GapReason.input_overflow in reasons
            else:
                assert isinstance(stream, EventStream)
                for fragment in stream.fragments:
                    with (path.parent / assets[fragment.asset].path).open() as lines:
                        stored[stream.event_kind].extend(
                            TypeAdapter(StoredEvent).validate_json(e) for e in lines
                        )
    for events in stored.values():
        assert [e.tick for e in events] == [1_000_100_000, 1_000_200_000, 1_000_300_000]
        assert [e.ordinal for e in events] == [0, 1, 2]
    assert isinstance(stored['midi'][0], MidiEvent)
    assert stored['midi'][0].data == [144, 60, 64]
    assert isinstance(stored['osc'][2], OscEvent)
    assert base64.b64decode(stored['osc'][2].data_b64) == b'buffered'
    assert stored['osc'][2].decoded[0].error
    smf = export_midi(
        destination / 'recording.toml', 'midi:keys', tmp_path / 'take.mid'
    )
    messages = [m for m in mido.MidiFile(smf).tracks[0] if not m.is_meta]
    assert [m.time for m in messages] == [0, 0, 1]
    edit = SourceSpec(
        id='take',
        record=destination / 'recording.toml',
        selector=RecordSelector(source='Mic', track='1'),
    )
    rendered = materialize_source(resolve_input(edit, tmp_path))
    soundfile.write(tmp_path / 'restored.wav', rendered.samples, 48000, subtype='FLOAT')
    actual, rate = soundfile.read(tmp_path / 'restored.wav')
    assert rate == 48000 and len(actual) == 384000
    np.testing.assert_array_equal(actual[48000:144000], 0)
    np.testing.assert_array_equal(actual[240000:336000], 0)


def test_interrupted_journal_preserves_closed_audio_and_reports_partial_file(
    tmp_path: Path,
) -> None:
    session = RecordingSession('partial', 0.0)
    journal = tmp_path / 'session-record.jsonl'
    session.start(journal, enabled=True)
    _audio(session, tmp_path, 0)
    session.write(
        session_record.AudioFileRecord(
            clock_id='audio',
            type='file_started',
            timestamp='later',
            stream_id='audio:Mic:1',
            format='wav',
            path=str(tmp_path / 'incomplete.wav'),
            frame_count=192000,
        )
    )
    session.record_writer.close()
    with journal.open('a') as target:
        target.write('{"type":')
    document, notes = prepare_recording(journal)
    assert document.body.state == 'open'
    assert document.body.unfinished_files[0].journal_path == 'incomplete.wav'
    assert verify_recording(document, tmp_path).audio_frames == 96000
    assert any('truncated final line' in n for n in notes)
    journal.write_text(journal.read_text() + '\n{}\n')
    with pytest.raises(RecsError, match='line'):
        prepare_recording(journal)


def _audio(
    session: RecordingSession,
    directory: Path,
    start: int,
    capture_id: str | None = None,
    channel: int = 1,
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48000, 'max_input_channels': 2}
    )
    writer = ChannelWriter(
        Cfg(formats=[Format.wav], output_directory=str(directory)),
        TimeSettings[int](
            quiet_before_start=0,
            quiet_after_end=0,
            stop_after_quiet=480000,
            shortest_file_time=1,
        ),
        Track(source, str(channel)),
    )
    tone = np.sin(np.arange(48000) * (2 * np.pi * 440 / 48000)) * 0.25
    for offset, active in ((0, True), (48000, False), (144000, True)):
        writer.receive_update(
            Block(block=tone if active else np.zeros(48000)),
            (start + offset + 48000) / 48000,
            should_record=active,
            timeline_frame=start + offset + 48000,
        )
    writer.stop()
    events = SourceFileEvents([writer], capture_id)
    files, records = events.new_files([writer], 32)
    for record in records:
        session.record_file_started(record, None)
    session.record_files(
        files,
        events.end_frames([writer]),
        events.end_timestamps([writer]),
        events.spans([writer]),
    )
    events.remember_finished_files([writer])
    for path in events.finished([writer]):
        session.record_file_finished(path)
    for timeline in events.timelines():
        session.write(timeline)


def test_short_capture_discard_is_sealed_evidence_not_an_interrupted_file(
    tmp_path: Path,
) -> None:
    session = RecordingSession('short', 0.0)
    journal = tmp_path / 'session-record.jsonl'
    session.start(journal, enabled=True)
    source = InputDevice(
        {'name': 'Mic', 'default_samplerate': 48000, 'max_input_channels': 1}
    )
    writer = ChannelWriter(
        Cfg(formats=[Format.wav], output_directory=str(tmp_path)),
        TimeSettings[int](shortest_file_time=96000),
        Track(source, '1'),
    )
    writer.receive_update(
        Block(block=np.ones(48000) * 0.25),
        1.0,
        should_record=True,
        timeline_frame=48000,
    )
    events = SourceFileEvents([writer])
    files, entries = events.new_files([writer], 32)
    for entry in entries:
        session.record_file_started(entry, None)
    writer.stop()
    events.remember_finished_files([writer])
    for path in events.discarded([writer]):
        session.record_file_discarded(path)
    for timeline in events.timelines():
        session.write(timeline)
    session.finish(1.0)
    assert session.record_errors == []
    document = read_recording(tmp_path / 'recording.toml')
    assert document.body.state == 'sealed'
    assert document.body.unfinished_files == []
    assert document.body.streams[0].gaps[0].reason == GapReason.short_capture
    assert len(document.assets) == 1
    assert explain(journal).explanations[0].reason == 'no files were recorded'


def test_key_capture_uses_common_events_and_preserves_observed_order(
    tmp_path: Path,
) -> None:
    session = RecordingSession('keys', 0.0)
    session.start(tmp_path / 'session-record.jsonl', enabled=True)
    for kind in ('key_pressed', 'key_released'):
        session.write(
            session_record.EventRecord(type=kind, timestamp='observed', key='a')
        )
    session.finish(1.0)
    assert session.record_errors == []
    document = read_recording(tmp_path / 'recording.toml')
    stream = document.body.streams[0]
    assert isinstance(stream, EventStream)
    assert stream.event_kind == 'key'
    assert verify_recording(document, tmp_path).event_count == 2
    payload = next(a for a in document.assets if a.id == stream.fragments[0].asset)
    events = [
        TypeAdapter(StoredEvent).validate_json(e)
        for e in (tmp_path / payload.path).read_text().splitlines()
    ]
    assert [(e.kind, e.ordinal, e.action) for e in events] == [
        ('key', 0, 'press'),
        ('key', 1, 'release'),
    ]


def test_reconnected_audio_keeps_independent_clock_evidence(tmp_path: Path) -> None:
    session = RecordingSession('reconnect', 0.0)
    session.start(tmp_path / 'session-record.jsonl', enabled=True)
    _audio(session, tmp_path / 'first', 0, capture_id='first')
    _audio(session, tmp_path / 'second', 0, capture_id='second')
    session.finish(10.0)
    assert session.record_errors == []
    path = tmp_path / 'recording.toml'
    document = read_recording(path)
    assert len(document.body.streams) == 2
    assert verify_recording(document, tmp_path).audio_frames == 192000
    edit = SourceSpec(
        id='take',
        record=path,
        selector=RecordSelector(source='Mic', track='1'),
    )
    with pytest.raises(
        RecsError, match='independent capture clocks require explicit alignment'
    ):
        resolve_input(edit, tmp_path)


def test_tracks_from_one_capture_share_the_device_clock(tmp_path: Path) -> None:
    session = RecordingSession('tracks', 0.0)
    session.start(tmp_path / 'session-record.jsonl', enabled=True)
    for channel in (1, 2):
        _audio(
            session, tmp_path / str(channel), 0, capture_id='device', channel=channel
        )
    session.finish(4.0)
    assert session.record_errors == []
    document = read_recording(tmp_path / 'recording.toml')
    streams = document.body.streams
    assert len(streams) == 2
    assert streams[0].stream.timebase == streams[1].stream.timebase
    observations = [
        o
        for o in document.body.clock_observations
        if o.timing_source == 'portaudio_callback_wall'
    ]
    assert len(observations) == 2
    assert all(o.source.timebase == streams[0].stream.timebase for o in observations)
    assert verify_recording(document, tmp_path).audio_frames == 192000


def test_midi_realtime_capture_is_preserved_and_smf_export_reports_limit(
    tmp_path: Path,
) -> None:
    session = RecordingSession('clock', 0.0)
    session.start(tmp_path / 'session-record.jsonl', enabled=True)
    port = MidiPort()
    midi = MidiRecorder(
        Cfg(),
        tmp_path / 'midi',
        lambda s: None,
        session.write,
        input_names=lambda: ['keys'],
        open_input=lambda n: port,
        capture_clock=lambda: 1000,
    )
    midi.start()
    port.messages.append(MidiPacket(mido.Message('clock'), 1500))
    midi.stop()
    session.finish(1.0)
    assert session.record_errors == []
    path = tmp_path / 'recording.toml'
    assert verify_recording(read_recording(path), tmp_path).event_count == 1
    destination = tmp_path / 'clock.mid'
    with pytest.raises(RecsError, match='cannot represent clock messages'):
        export_midi(path, 'midi:keys', destination)
    assert not destination.exists()
