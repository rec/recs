from collections import deque

import pytest

from recs.base import audio_stream
from recs.base.audio_stream import (
    MAX_HEADER_BYTES,
    MAX_PAYLOAD_BYTES,
    PREFIX,
    AudioHeader,
    encode_message,
    read_message,
)


class FragmentedSocket:
    def __init__(self, data: bytes) -> None:
        self.data = deque(data)

    def settimeout(self, timeout: float) -> None:
        pass

    def recv(self, length: int) -> bytes:
        return bytes([self.data.popleft()]) if self.data else b''


def test_protocol_reassembles_fragmented_headers() -> None:
    header = AudioHeader(type='ready', clock_id='capture')
    result, payload = read_message(FragmentedSocket(encode_message(header)), 1)
    assert result == header
    assert payload == b''


@pytest.mark.parametrize(
    'header_length,payload_length',
    [
        (0, 0),
        (MAX_HEADER_BYTES + 1, 0),
        (1, MAX_PAYLOAD_BYTES + 1),
    ],
)
def test_protocol_rejects_oversize_lengths_before_reading_payload(
    header_length: int, payload_length: int
) -> None:
    with pytest.raises(ValueError, match='length'):
        read_message(FragmentedSocket(PREFIX.pack(header_length, payload_length)), 1)


def test_protocol_applies_one_deadline_to_the_whole_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = iter([0.0, 0.0, 0.2])
    monkeypatch.setattr(audio_stream, 'monotonic', lambda: next(ticks))
    with pytest.raises(TimeoutError, match='deadline'):
        read_message(FragmentedSocket(encode_message(AudioHeader(type='ready'))), 0.1)


def test_protocol_reports_eof_on_partial_frame() -> None:
    with pytest.raises(EOFError):
        read_message(FragmentedSocket(PREFIX.pack(20, 0) + b'{'), 1)
