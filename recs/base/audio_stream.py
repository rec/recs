"""Versioned local PCM protocol and a client with no capture dependencies."""

import json
import socket
import struct
from time import monotonic
from typing import Literal, Self

from pydantic import BaseModel, Field

VERSION = 1
MAX_HEADER_BYTES = 4096
MAX_PAYLOAD_BYTES = 262_144
MAX_AUDIO_AGE_SECONDS = 0.25
PREFIX = struct.Struct('!II')


class AudioSubscription(BaseModel, frozen=True):
    subscription_id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=512)
    clock_id: str = Field(min_length=1, max_length=128)
    instance_token: str = Field(min_length=1, max_length=128)
    port: int = Field(gt=0, le=65535)
    sample_rate: int = Field(gt=0, le=192_000)
    channels: list[int] = Field(min_length=1, max_length=2)
    generation: int = Field(gt=0)
    expires_at: float = Field(allow_inf_nan=False)
    secret: str = Field(default='', repr=False, max_length=64)
    host: Literal['127.0.0.1'] = '127.0.0.1'
    version: Literal[1] = VERSION
    sample_format: Literal['f32le'] = 'f32le'


class AudioHeader(BaseModel, frozen=True):
    type: Literal['hello', 'ready', 'audio']
    clock_id: str = Field(default='', max_length=128)
    sequence: int = Field(default=0, ge=0)
    start_frame: int = Field(default=0, ge=0)
    frames: int = Field(default=0, ge=0)
    timestamp: float = Field(default=0, allow_inf_nan=False)
    offered_at: float = Field(default=0, allow_inf_nan=False)
    input_status: str = Field(default='', max_length=512)
    subscription: AudioSubscription | None = None


class AudioClient:
    """One live subscription. Any incomplete/invalid read closes the connection.

    Frame jumps report known gaps; input_status may report unknown PortAudio loss.
    The caller owns reconnects, outage policy, resampling, and encoder buffering.
    """

    def __init__(self, subscription: AudioSubscription, timeout: float = 1.0) -> None:
        self.subscription = subscription
        self.timeout = timeout
        self.socket = socket.create_connection(
            (subscription.host, subscription.port), timeout=timeout
        )
        try:
            self.socket.sendall(
                encode_message(AudioHeader(type='hello', subscription=subscription))
            )
            header, payload = read_message(self.socket, timeout)
            if (
                header.type != 'ready'
                or header.clock_id != subscription.clock_id
                or payload
            ):
                raise ValueError('Invalid audio subscription acknowledgement')
        except (OSError, ValueError, EOFError, MemoryError):
            self.close()
            raise
        self.sequence = 0
        self.end_frame: int | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def receive(self) -> tuple[AudioHeader, bytes]:
        try:
            header, payload = read_message(self.socket, self.timeout)
            if (
                header.type == 'audio'
                and not 0 <= monotonic() - header.offered_at <= MAX_AUDIO_AGE_SECONDS
            ):
                raise TimeoutError('Audio consumer fell behind the live edge')
            if (
                header.type != 'audio'
                or header.clock_id != self.subscription.clock_id
                or header.sequence != self.sequence
                or not header.frames
                or len(payload) != header.frames * len(self.subscription.channels) * 4
                or (self.end_frame is not None and header.start_frame < self.end_frame)
            ):
                raise ValueError('Invalid audio frame')
        except (OSError, ValueError, EOFError, MemoryError):
            self.close()
            raise
        self.sequence += 1
        self.end_frame = header.start_frame + header.frames
        return header, payload

    def close(self) -> None:
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()


def encode_message(header: AudioHeader, payload: bytes = b'') -> bytes:
    encoded = header.model_dump_json(exclude_defaults=True).encode()
    if len(encoded) > MAX_HEADER_BYTES or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError('Audio message exceeds the size limit')
    return PREFIX.pack(len(encoded), len(payload)) + encoded + payload


def read_message(conn: socket.socket, timeout: float) -> tuple[AudioHeader, bytes]:
    deadline = monotonic() + timeout
    header_length, payload_length = PREFIX.unpack(
        _read_exact(conn, PREFIX.size, deadline)
    )
    if not 0 < header_length <= MAX_HEADER_BYTES or payload_length > MAX_PAYLOAD_BYTES:
        raise ValueError('Invalid audio message length')
    header = AudioHeader.model_validate_json(_read_exact(conn, header_length, deadline))
    if header.type != 'audio' and payload_length:
        raise ValueError('Unexpected audio payload')
    return header, _read_exact(conn, payload_length, deadline)


def subscription_signature_data(subscription: AudioSubscription) -> bytes:
    return json.dumps(
        subscription.model_dump(exclude={'secret'}),
        sort_keys=True,
        separators=(',', ':'),
    ).encode()


def _read_exact(conn: socket.socket, length: int, deadline: float) -> bytes:
    result = bytearray()
    while len(result) < length:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise TimeoutError('Audio message deadline expired')
        # Closing a descriptor in another thread need not wake a timed recv on
        # every OS. Short waits also bound cancellation without losing framing.
        conn.settimeout(min(remaining, 0.05))
        try:
            part = conn.recv(length - len(result))
        except TimeoutError:
            continue
        if not part:
            raise EOFError('Audio source closed')
        result.extend(part)
    return bytes(result)
