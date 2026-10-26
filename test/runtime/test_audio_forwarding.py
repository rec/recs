import multiprocessing
import socket
import threading
from collections.abc import Callable, Iterator
from multiprocessing import Pipe
from pathlib import Path
from time import monotonic, sleep

import numpy as np
import pytest
import soundfile
from threa import Runnable

from recs.base.audio_stream import (
    MAX_HEADER_BYTES,
    PREFIX,
    AudioClient,
    AudioHeader,
    encode_message,
)
from recs.base.errors import RecsError
from recs.cfg import mic_mute
from recs.cfg.cfg import Cfg
from recs.cfg.device import InputDevice
from recs.cfg.source import Update
from recs.cfg.track import Track
from recs.runtime import audio_forwarding, audio_source, input_buffer
from recs.runtime.audio_forwarding import AudioForwarder, AudioMailbox
from recs.runtime.audio_source import AudioSource
from recs.runtime.input_buffer import BufferedUpdate, InputBuffer
from recs.runtime.source_messages import SourceControl
from recs.runtime.source_recorder import SourceRecorder
from recs.runtime.source_transport import SourceUpdateTransport


@pytest.fixture
def audio(tmp_path: Path) -> np.ndarray:
    t = np.arange(48_000) / 48_000
    array = np.column_stack((np.sin(t * 20), np.cos(t * 30))).astype(np.float32) / 2
    array[12_000:36_000] = 0
    path = tmp_path / 'input.wav'
    soundfile.write(path, array, 48_000, subtype='FLOAT')
    return soundfile.read(path, dtype='float32', always_2d=True)[0]


@pytest.fixture
def forwarding() -> Iterator[tuple[AudioSource, AudioForwarder]]:
    source = AudioSource('Mic', 48_000, 2)
    try:
        with AudioForwarder(
            source.listener,
            source.key,
            source.counters,
            source.clock_id,
            source.source,
            source.sample_rate,
            source.channels,
            threading.Event(),
            source.source,
        ) as forwarder:
            yield source, forwarder
        assert not forwarder.thread.is_alive()
    finally:
        source.close()


@pytest.mark.parametrize('channels', [[1], [2, 1]])
@pytest.mark.parametrize('dtype', ['float32', 'int16'])
def test_live_pcm_preserves_quiet_channel_order_and_capture_frames(
    forwarding: tuple[AudioSource, AudioForwarder],
    audio: np.ndarray,
    tmp_path: Path,
    channels: list[int],
    dtype: str,
) -> None:
    source, forwarder = forwarding
    array = audio if dtype == 'float32' else (audio * 32767).astype('int16')
    before = array.copy()
    buffer = InputBuffer(Cfg(audio_buffer_seconds=0.1), 48_000)
    buffer.forward_audio = forwarder.offer
    output: list[np.ndarray] = []
    with AudioClient(source.subscribe(channels, 'instance')) as client:
        for start in range(0, len(array), 960):
            buffer.put(Update(array[start : start + 960], 100 + start / 48_000))
            header, payload = client.receive()
            assert header.start_frame == start
            assert header.frames == 960
            assert header.timestamp == pytest.approx(100 + start / 48_000)
            output.append(
                np.frombuffer(payload, dtype='<f4').reshape(-1, len(channels))
            )
    result = np.concatenate(output)
    expected = array[:, [c - 1 for c in channels]].astype(np.float32)
    if dtype == 'int16':
        expected /= 32768
    np.testing.assert_array_equal(result, expected)
    np.testing.assert_array_equal(array, before)
    soundfile.write(tmp_path / 'forwarded.wav', result, 48_000, subtype='FLOAT')
    assert (
        buffer.stats.dropped_frames > 0
    )  # The full recording queue did not block PCM.
    assert source.status()['sent_frames'] == 48_000
    assert 'secret' not in str(source.status())


def test_mailbox_keeps_bounded_fresh_references_without_block_copies(
    audio: np.ndarray,
) -> None:
    mailbox = AudioMailbox(48_000)
    for start in range(0, len(audio), 960):
        mailbox.offer(
            BufferedUpdate(Update(audio[start : start + 960], 1), start, start + 960)
        )
    assert mailbox.frames == 4800
    assert mailbox.bytes <= audio_forwarding.MAX_BUFFER_BYTES
    assert mailbox.dropped == 43_200
    item = mailbox.take()
    assert item is not None
    assert item[0].start_frame == 43_200
    assert np.shares_memory(item[0].update.array, audio)
    mailbox.lock.acquire()
    try:
        mailbox.offer(BufferedUpdate(Update(audio[:960], 1), 0, 960))
    finally:
        mailbox.lock.release()
    assert mailbox.dropped == 44_160
    mailbox.clear(2)
    mailbox.offer(BufferedUpdate(Update(audio[:960], 1), 0, 960), generation=1)
    assert mailbox.take() is None  # An old callback cannot repopulate a revoked queue.


def test_oversize_block_and_memory_reserve_drop_forwarding_without_blocking_recording(
    forwarding: tuple[AudioSource, AudioForwarder],
    audio: np.ndarray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, forwarder = forwarding
    buffer = InputBuffer(Cfg(), 48_000)
    buffer.forward_audio = forwarder.offer
    with AudioClient(source.subscribe([1], 'instance')):
        buffer.put(Update(audio, 1))
        assert buffer.get(block=False).update.array is audio
        assert forwarder.mailbox.dropped == 48_000
        monkeypatch.setattr(input_buffer.memory, 'available_bytes', lambda: 0)
        buffer.last_memory_check = float('-inf')
        buffer.check_memory()
        buffer.put(Update(audio, 2))
        assert buffer.stats.dropped_frames == 48_000
        assert forwarder.mailbox.dropped == 48_000


def test_subscription_is_single_use_and_reconnect_never_replays_audio(
    forwarding: tuple[AudioSource, AudioForwarder],
    audio: np.ndarray,
) -> None:
    source, forwarder = forwarding
    offer = source.subscribe([1, 2], 'instance')
    with AudioClient(offer) as client:
        with pytest.raises(RecsError, match='already has'):
            source.subscribe([1], 'instance')
        forwarder.offer(
            BufferedUpdate(Update(audio[:960], 1, 'input overflow'), 0, 960)
        )
        header, _ = client.receive()
        assert header.input_status == 'input overflow'
        assert source.unsubscribe(offer.subscription_id)
        with pytest.raises((EOFError, OSError)):
            client.receive()
    with pytest.raises((EOFError, OSError)):
        AudioClient(offer)
    replacement = source.subscribe([2, 1], 'instance')
    with AudioClient(replacement) as client:
        forwarder.offer(BufferedUpdate(Update(audio[960:1920], 2), 960, 1920))
        header, _ = client.receive()
        assert header.start_frame == 960
        assert header.sequence == 0
    assert not source.unsubscribe(offer.subscription_id)


@pytest.mark.parametrize(
    'bad_offer', ['secret', 'channels', 'expired', 'oversized', 'partial']
)
def test_bad_handshake_does_not_stop_capture_or_consume_valid_offer(
    forwarding: tuple[AudioSource, AudioForwarder],
    bad_offer: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, forwarder = forwarding
    offer = source.subscribe([1], 'instance')
    if bad_offer == 'expired':
        monkeypatch.setattr(audio_source, 'OFFER_SECONDS', -1)
        source.unsubscribe(offer.subscription_id)
        offer = source.subscribe([1], 'instance')
    with socket.create_connection((offer.host, offer.port), timeout=1) as conn:
        conn.settimeout(1)
        if bad_offer == 'oversized':
            conn.sendall(PREFIX.pack(MAX_HEADER_BYTES + 1, 0))
        elif bad_offer == 'partial':
            conn.sendall(b'\x00')
        else:
            changed = (
                offer.model_copy(update={'secret': '0' * 64})
                if bad_offer == 'secret'
                else offer.model_copy(update={'channels': [2]})
                if bad_offer == 'channels'
                else offer
            )
            conn.sendall(
                encode_message(AudioHeader(type='hello', subscription=changed))
            )
        assert conn.recv(1) == b''
    assert forwarder.thread.is_alive()
    assert source.status()['error'] is None


def test_stalled_partial_send_closes_only_subscriber(
    audio: np.ndarray,
) -> None:
    class StalledSocket:
        def settimeout(self, timeout: float) -> None:
            pass

        def sendall(self, data: bytes) -> None:
            raise TimeoutError('partial write')

        def close(self) -> None:
            pass

    source = AudioSource('Mic', 48_000, 2)
    forwarder = AudioForwarder(
        source.listener,
        source.key,
        source.counters,
        source.clock_id,
        source.source,
        source.sample_rate,
        source.channels,
        threading.Event(),
        source.source,
    )
    try:
        forwarder.subscription = source.subscribe([1], 'instance')
        forwarder.client = StalledSocket()
        forwarder.send(BufferedUpdate(Update(audio[:960], 1), 0, 960), monotonic())
        assert forwarder.subscription is None
        assert source.status()['error'] == 'Consumer stalled or disconnected'
    finally:
        forwarder.close()
        source.close()


def test_client_rejects_stale_kernel_buffered_audio(
    forwarding: tuple[AudioSource, AudioForwarder],
    audio: np.ndarray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from recs.base import audio_stream

    source, forwarder = forwarding
    with AudioClient(source.subscribe([1], 'instance')) as client:
        forwarder.offer(BufferedUpdate(Update(audio[:960], 1), 0, 960))
        clock = monotonic()
        monkeypatch.setattr(audio_stream, 'monotonic', lambda: clock + 1)
        with pytest.raises(TimeoutError, match='live edge'):
            client.receive()


class ManualInput(Runnable):
    def __init__(self, callback: Callable[[Update], None]) -> None:
        self.callback = callback
        self.ready = threading.Event()

    def start(self) -> None:
        super().start()
        self.ready.set()


@pytest.mark.parametrize(
    'mode', ['disabled', 'active', 'disconnected', 'stalled', 'suspended']
)
def test_forwarding_does_not_change_recorded_wav(
    mode: str,
    audio: np.ndarray,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = InputDevice(
        {'name': 'Mic', 'max_input_channels': 2, 'default_samplerate': 48_000}
    )
    streams: list[ManualInput] = []

    def input_stream(
        sdtype: object, update_callback: Callable[[Update], None]
    ) -> ManualInput:
        stream = ManualInput(update_callback)
        streams.append(stream)
        return stream

    source.input_stream = input_stream
    controls, controls_writer = Pipe(duplex=False)
    updates_reader, updates = Pipe(duplex=False)
    owner = AudioSource('Mic', 48_000, 2) if mode != 'disabled' else None
    stop = threading.Event()
    cfg = Cfg(
        record_everything=True,
        formats=['wav'],
        subtype='float',
        output_directory=str(tmp_path / 'recorded'),
        shortest_file_time=0,
        quiet_before_start=0,
        quiet_after_end=0,
    )
    rec = SourceRecorder(
        cfg,
        controls,
        tmp_path / 'session',
        stop,
        [Track(source, '1-2')],
        SourceUpdateTransport(updates),
        audio_listener=owner.listener if owner else None,
        audio_key=owner.key if owner else b'',
        audio_counters=owner.counters if owner else None,
        capture_id=owner.capture_id if owner else None,
    )
    errors: list[BaseException] = []

    def record() -> None:
        try:
            rec.run()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=record)
    sender_entered = threading.Event()
    release_sender = threading.Event()
    if mode == 'stalled':
        assert rec.audio_forwarder is not None

        def stalled_send(block: BufferedUpdate, offered: float) -> None:
            sender_entered.set()
            release_sender.wait(2)

        monkeypatch.setattr(rec.audio_forwarder, 'send', stalled_send)
    thread.start()
    client = None
    try:
        assert streams[0].ready.wait(2)
        if owner:
            client = AudioClient(owner.subscribe([2, 1], 'instance'))
            if mode == 'disconnected':
                client.close()
        if mode == 'suspended':
            controls_writer.send(SourceControl(writing_enabled=False))
            deadline = monotonic() + 2
            while rec.writing_enabled and monotonic() < deadline:
                sleep(0.005)
            assert not rec.writing_enabled
        for start in range(0, len(audio), 960):
            streams[0].callback(
                Update(audio[start : start + 960], 100 + start / 48_000)
            )
            if mode in ('active', 'suspended'):
                assert client is not None
                client.receive()
            elif mode == 'stalled' and start == 0:
                assert sender_entered.wait(1)
        if mode == 'suspended':
            controls_writer.send(
                SourceControl(
                    session_directory=tmp_path / 'replacement',
                    writing_enabled=True,
                    recovery_failover=True,
                )
            )
        deadline = monotonic() + 2
        while rec.sample_count < len(audio) and monotonic() < deadline:
            sleep(0.005)
        assert rec.sample_count == len(audio)
        release_sender.set()
        stop.set()
        thread.join(3)
        assert not thread.is_alive()
        assert errors == []
        assert len(streams) == 1
        files = rec.channel_writers[0].files_written
        assert len(files) == 1
        recorded, rate = soundfile.read(files[0], dtype='float32', always_2d=True)
        assert rate == 48_000
        np.testing.assert_array_equal(recorded, audio)
        if owner:
            from recs.recording.capture_events import capture_clock_id

            assert capture_clock_id(rec.file_events.capture_id) == owner.clock_id
    finally:
        release_sender.set()
        stop.set()
        thread.join(3)
        if client:
            client.close()
        if owner:
            owner.close()
        for connection in (controls, controls_writer, updates_reader, updates):
            connection.close()


def run_forwarding_child(
    listener: socket.socket,
    key: bytes,
    counters: object,
    clock_id: str,
    stop: object,
    audio: np.ndarray,
) -> None:
    with AudioForwarder(
        listener, key, counters, clock_id, 'Mic', 48_000, 2, stop, 'Mic'
    ) as forwarder:
        deadline = monotonic() + 5
        while forwarder.subscription is None and monotonic() < deadline:
            sleep(0.005)
        for start in range(0, len(audio), 960):
            forwarder.offer(
                BufferedUpdate(
                    Update(audio[start : start + 960], 1 + start / 48_000),
                    start,
                    start + 960,
                )
            )
            while (
                counters[audio_forwarding.SENT] < start + 960 and monotonic() < deadline
            ):
                sleep(0.005)
        stop.wait(5)


def test_spawned_capture_process_shares_socket_capabilities_and_health(
    audio: np.ndarray, tmp_path: Path
) -> None:
    context = multiprocessing.get_context('spawn')
    stop = context.Event()
    source = AudioSource('Mic', 48_000, 2)
    process = context.Process(
        target=run_forwarding_child,
        args=(
            source.listener,
            source.key,
            source.counters,
            source.clock_id,
            stop,
            audio,
        ),
    )
    process.start()
    try:
        with AudioClient(source.subscribe([1, 2], 'instance'), timeout=5) as client:
            blocks = [
                np.frombuffer(client.receive()[1], dtype='<f4').reshape(-1, 2)
                for _ in range(50)
            ]
        result = np.concatenate(blocks)
        np.testing.assert_array_equal(result, audio)
        soundfile.write(tmp_path / 'spawned.wav', result, 48_000, subtype='FLOAT')
        assert source.status()['sent_frames'] == 48_000
    finally:
        stop.set()
        process.join(3)
        if process.is_alive():
            process.terminate()
            process.join(2)
        source.close()
    assert process.exitcode == 0


def test_saved_mic_mute_revokes_an_already_connected_client(
    forwarding: tuple[AudioSource, AudioForwarder],
) -> None:
    source, forwarder = forwarding
    with AudioClient(source.subscribe([1], 'instance')) as client:
        mic_mute.save(mic_mute.MicMute(device_name='Mic', is_muted=True))
        with pytest.raises((EOFError, OSError)):
            client.receive()
    assert forwarder.thread.is_alive()
    assert (
        source.status()['error']
        == 'Microphone muted or mic-mute configuration unreadable'
    )
    mic_mute.save(mic_mute.MicMute(device_name='Mic', is_muted=False))
    deadline = monotonic() + 1
    while source.status()['error'] is not None and monotonic() < deadline:
        sleep(0.005)
    assert source.status()['error'] is None
    with AudioClient(source.subscribe([1], 'instance')):
        pass


def test_client_close_wakes_a_blocked_reader(
    forwarding: tuple[AudioSource, AudioForwarder],
) -> None:
    source, _ = forwarding
    client = AudioClient(source.subscribe([1], 'instance'), timeout=5)
    reading = threading.Event()
    outcomes: list[str] = []

    def read() -> None:
        reading.set()
        try:
            client.receive()
        except (EOFError, OSError):
            outcomes.append('closed')

    thread = threading.Thread(target=read)
    thread.start()
    try:
        assert reading.wait(1)
        client.close()
        thread.join(0.5)
        assert not thread.is_alive()
        assert outcomes == ['closed']
    finally:
        client.close()
        thread.join(5)


def test_tiny_forwarded_blocks_are_batched_without_crossing_loss_boundaries(
    audio: np.ndarray, tmp_path: Path
) -> None:
    mailbox = AudioMailbox(48_000)
    for frame in range(481):
        mailbox.offer(
            BufferedUpdate(
                Update(
                    audio[frame : frame + 1],
                    frame / 48_000,
                    'input overflow' if frame == 300 else '',
                ),
                frame,
                frame + 1,
            )
        )
    batches = []
    while (batch := mailbox.take()) is not None:
        batches.append(batch[0])
    assert [(b.start_frame, b.end_frame) for b in batches] == [
        (0, 240),
        (240, 300),
        (300, 481),
    ]
    assert [b.update.status for b in batches] == ['', '', 'input overflow']
    for frame in range(481, len(audio), mailbox.max_frames):
        end = min(frame + mailbox.max_frames, len(audio))
        mailbox.offer(
            BufferedUpdate(Update(audio[frame:end], frame / 48_000), frame, end)
        )
        batch = mailbox.take()
        assert batch is not None
        batches.append(batch[0])
    actual = np.concatenate([b.update.array for b in batches])
    np.testing.assert_array_equal(actual, audio)
    soundfile.write(tmp_path / 'forwarded.wav', actual, 48_000, subtype='FLOAT')


def test_stalled_optional_mailbox_does_not_block_capture(
    audio: np.ndarray, tmp_path: Path
) -> None:
    buffer = InputBuffer(Cfg(), 48_000)
    mailbox = AudioMailbox(48_000)
    buffer.forward_audio = mailbox.offer
    finished = threading.Event()

    def capture() -> None:
        buffer.put(Update(audio, 0.0))
        finished.set()

    with mailbox.lock:
        callback = threading.Thread(target=capture)
        callback.start()
        assert finished.wait(1)
    callback.join()
    retained = buffer.get(block=False)
    assert retained.end_frame == 48_000
    np.testing.assert_array_equal(retained.update.array, audio)
    soundfile.write(
        tmp_path / 'captured.wav', retained.update.array, 48_000, subtype='FLOAT'
    )
    assert mailbox.dropped == 48_000
    assert buffer.stats.dropped_frames == 0
