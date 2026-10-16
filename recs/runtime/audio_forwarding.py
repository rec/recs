"""Bounded capture ingress mailbox and isolated local PCM sender."""

import hmac
import socket
import threading
from collections import deque
from collections.abc import MutableSequence
from time import monotonic, monotonic_ns, sleep
from typing import Protocol, Self

import numpy as np

from recs.base.audio_stream import (
    MAX_AUDIO_AGE_SECONDS,
    AudioHeader,
    AudioSubscription,
    encode_message,
    read_message,
    subscription_signature_data,
)
from recs.base.errors import RecsError
from recs.cfg import mic_mute

from .input_buffer import BufferedUpdate

BUFFER_SECONDS = 0.1
MAX_BUFFER_BYTES = 1_048_576
MAX_BLOCKS = 128
POLL_SECONDS = 0.005
HANDSHAKE_SECONDS = 0.2
# Parent writes DESIRED; callback writes capture/block observations; worker writes
# delivery observations. Health counters are approximate, not a durable journal.
DESIRED, ACCEPTED, STATE, SENT, DROPPED, RETAINED, LAST_SEND, ERROR = range(8)
CAPTURE_FRAME, CAPTURE_TIME = 8, 9
BLOCK_BYTES, BLOCK_FRAMES = 10, 11
IDLE, CONNECTED, CLOSED, FAILED = range(4)


class StopEvent(Protocol):
    def is_set(self) -> bool: ...


class AudioMailbox:
    def __init__(self, sample_rate: int) -> None:
        self.max_frames = max(1, int(sample_rate * BUFFER_SECONDS))
        self.lock = threading.Lock()
        self.blocks: deque[tuple[BufferedUpdate, float]] = deque()
        self.frames = 0
        self.bytes = 0
        self.dropped = 0
        self.generation = 0

    def offer(self, block: BufferedUpdate, generation: int = 0) -> None:
        frames = len(block.update.array)
        size = block.update.array.nbytes
        if not self.lock.acquire(blocking=False):
            self.dropped += frames
            return
        try:
            if generation != self.generation:
                return
            if frames > self.max_frames or size > MAX_BUFFER_BYTES:
                self.dropped += frames
                return
            while self.blocks and (
                self.frames + frames > self.max_frames
                or self.bytes + size > MAX_BUFFER_BYTES
                or len(self.blocks) >= MAX_BLOCKS
            ):
                old, _ = self.blocks.popleft()
                self.frames -= len(old.update.array)
                self.bytes -= old.update.array.nbytes
                self.dropped += len(old.update.array)
            self.blocks.append((block, monotonic()))
            self.frames += frames
            self.bytes += size
        finally:
            self.lock.release()

    def take(self) -> tuple[BufferedUpdate, float] | None:
        with self.lock:
            if not self.blocks:
                return None
            block, offered = self.blocks.popleft()
            self.frames -= len(block.update.array)
            self.bytes -= block.update.array.nbytes
            return block, offered

    def clear(self, generation: int = 0) -> None:
        with self.lock:
            self.generation = generation
            self.blocks.clear()
            self.frames = self.bytes = 0


class AudioForwarder:
    def __init__(
        self,
        listener: socket.socket,
        key: bytes,
        counters: MutableSequence[int],
        clock_id: str,
        source: str,
        sample_rate: int,
        channels: int,
        stop_event: StopEvent,
        device_name: str,
    ) -> None:
        self.listener = listener.dup()
        self.listener.settimeout(0.05)
        self.key = key
        self.counters = counters
        self.clock_id = clock_id
        self.source = source
        self.sample_rate = sample_rate
        self.channels = channels
        self.stop_event = stop_event
        self.device_name = device_name
        self.next_mute_check = 0.0
        self.mailbox = AudioMailbox(sample_rate)
        self.stopped = threading.Event()
        self.thread = threading.Thread(
            target=self.run, daemon=True, name='AudioForwarding'
        )
        self.client: socket.socket | None = None
        self.subscription: AudioSubscription | None = None
        self.used_generation = 0
        self.sequence = 0
        self.dropped = 0
        self.next_accept = 0.0

    def __enter__(self) -> Self:
        try:
            self.thread.start()
        except RuntimeError:
            self.counters[ERROR] = 1
            self.counters[STATE] = FAILED
            self.close()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def offer(self, block: BufferedUpdate) -> None:
        self.counters[CAPTURE_FRAME] = block.end_frame
        self.counters[CAPTURE_TIME] = monotonic_ns()
        self.counters[BLOCK_BYTES] = block.update.array.nbytes
        self.counters[BLOCK_FRAMES] = len(block.update.array)
        subscription = self.subscription
        if (
            subscription is not None
            and self.counters[DESIRED] == subscription.generation
            and not self.stopped.is_set()
        ):
            try:
                self.mailbox.offer(block, subscription.generation)
            except MemoryError:
                # No allocation or logging on the callback's exceptional path.
                self.counters[ERROR] = 2
                self.counters[STATE] = FAILED
                self.stopped.set()

    def run(self) -> None:
        try:
            while not self.stopped.is_set() and not self.stop_event.is_set():
                if (
                    self.subscription is not None or self.counters[ERROR] == 4
                ) and monotonic() >= self.next_mute_check:
                    self.next_mute_check = monotonic() + 0.2
                    if self.muted():
                        self.disconnect()
                    elif self.counters[ERROR] == 4:
                        self.counters[ERROR] = 0
                if self.subscription is not None and (
                    self.counters[DESIRED] != self.subscription.generation
                ):
                    self.disconnect()
                if self.client is None:
                    self.accept()
                elif (item := self.mailbox.take()) is not None:
                    block, offered = item
                    if monotonic() - offered > BUFFER_SECONDS:
                        self.dropped += len(block.update.array)
                    else:
                        self.send(block, offered)
                    del block, item
                else:
                    # Detect a dead consumer even when the source stops producing.
                    self.client.settimeout(POLL_SECONDS)
                    try:
                        self.client.recv(1)
                    except TimeoutError:
                        pass
                    except OSError:
                        self.disconnect()
                    else:
                        self.disconnect()
                self.counters[DROPPED] = self.mailbox.dropped + self.dropped
                self.counters[RETAINED] = self.mailbox.bytes
        except (OSError, ValueError, MemoryError):
            if not self.stopped.is_set() and not self.stop_event.is_set():
                self.counters[ERROR] = 2
                self.counters[STATE] = FAILED
        finally:
            self.disconnect()
            self.listener.close()

    def accept(self) -> None:
        if monotonic() < self.next_accept:
            sleep(POLL_SECONDS)
            return
        try:
            client, _ = self.listener.accept()
        except TimeoutError:
            return
        self.next_accept = monotonic() + 0.05
        try:
            client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65_536)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            header, payload = read_message(client, HANDSHAKE_SECONDS)
            offer = header.subscription
            if (
                header.type != 'hello'
                or payload
                or offer is None
                or offer.clock_id != self.clock_id
                or offer.source != self.source
                or offer.sample_rate != self.sample_rate
                or offer.generation != self.counters[DESIRED]
                or offer.generation <= self.used_generation
                or monotonic() >= offer.expires_at
                or len(set(offer.channels)) != len(offer.channels)
                or any(c < 1 or c > self.channels for c in offer.channels)
                or not hmac.compare_digest(
                    offer.secret,
                    hmac.digest(
                        self.key, subscription_signature_data(offer), 'sha256'
                    ).hex(),
                )
            ):
                raise ValueError('Invalid audio subscription')
            self.used_generation = offer.generation
            if self.muted():
                raise ValueError('Microphone is muted')
            self.mailbox.clear(offer.generation)
            client.settimeout(HANDSHAKE_SECONDS)
            client.sendall(
                encode_message(AudioHeader(type='ready', clock_id=self.clock_id))
            )
            if self.counters[DESIRED] != offer.generation or self.stop_event.is_set():
                raise ValueError('Audio subscription was cancelled')
            self.client = client
            self.sequence = 0
            self.counters[STATE] = CONNECTED
            self.counters[ACCEPTED] = offer.generation
            self.counters[ERROR] = 0
            self.subscription = offer
        except (OSError, EOFError, ValueError):
            client.close()

    def send(self, block: BufferedUpdate, offered: float) -> None:
        assert self.client is not None and self.subscription is not None
        array = block.update.array
        pcm = array[:, [c - 1 for c in self.subscription.channels]].astype('<f4')
        if np.issubdtype(array.dtype, np.integer):
            pcm /= float(1 << (array.dtype.itemsize * 8 - 1))
        chunk_frames = max(1, self.sample_rate // 50)
        try:
            for start in range(0, len(pcm), chunk_frames):
                if (
                    self.counters[DESIRED] != self.subscription.generation
                    or self.stop_event.is_set()
                    or self.stopped.is_set()
                ):
                    self.disconnect()
                    return
                remaining = offered + MAX_AUDIO_AGE_SECONDS - monotonic()
                if remaining <= 0:
                    raise TimeoutError('Audio consumer fell behind')
                part = pcm[start : start + chunk_frames]
                header = AudioHeader(
                    type='audio',
                    clock_id=self.clock_id,
                    sequence=self.sequence,
                    start_frame=block.start_frame + start,
                    frames=len(part),
                    timestamp=block.update.timestamp + start / self.sample_rate,
                    offered_at=offered,
                    input_status=block.update.status,
                )
                self.client.settimeout(remaining)
                self.client.sendall(encode_message(header, part.tobytes()))
                self.sequence += 1
                self.counters[SENT] += len(part)
                self.counters[LAST_SEND] = monotonic_ns()
        except OSError:
            self.counters[ERROR] = 3
            self.disconnect()

    def muted(self) -> bool:
        try:
            mute = mic_mute.load()
        except RecsError:
            self.counters[ERROR] = 4
            return True
        if mute is not None and mute.is_muted and mute.device_name == self.device_name:
            self.counters[ERROR] = 4
            return True
        return False

    def disconnect(self) -> None:
        self.subscription = None
        self.mailbox.clear()
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.counters[STATE] != FAILED:
            self.counters[STATE] = CLOSED
        self.counters[RETAINED] = 0

    def close(self) -> None:
        self.stopped.set()
        client = self.client
        if client is not None:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.listener.close()
        if self.thread.ident is not None:
            self.thread.join(MAX_AUDIO_AGE_SECONDS + HANDSHAKE_SECONDS + 0.1)
        self.mailbox.clear()
