"""Parent-side ownership of one source's bounded audio subscription."""

import hmac
import multiprocessing
import secrets
import socket
import uuid
from collections.abc import MutableSequence
from time import monotonic, monotonic_ns
from typing import cast

from recs.base.audio_stream import AudioSubscription, subscription_signature_data
from recs.base.errors import RecsError
from recs.recording.capture_events import capture_clock_id

from . import audio_forwarding

MAX_SUBSCRIPTIONS = 8
OFFER_SECONDS = 5.0


class AudioSource:
    def __init__(self, source: str, sample_rate: int, channels: int) -> None:
        self.source = source
        self.sample_rate = sample_rate
        self.channels = channels
        self.capture_id = uuid.uuid4().hex
        self.clock_id = capture_clock_id(self.capture_id)
        self.key = secrets.token_bytes(32)
        self.counters = cast(
            MutableSequence[int], multiprocessing.Array('q', 12, lock=False)
        )
        self.generation = 0
        self.subscription: AudioSubscription | None = None
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.listener.bind(('127.0.0.1', 0))
            self.listener.listen(1)
        except OSError:
            self.listener.close()
            raise

    @property
    def active(self) -> bool:
        offer = self.subscription
        if (
            offer is None
            or self.counters[audio_forwarding.STATE] == audio_forwarding.FAILED
        ):
            return False
        if self.counters[audio_forwarding.ACCEPTED] == offer.generation:
            return self.counters[audio_forwarding.STATE] == audio_forwarding.CONNECTED
        return monotonic() < offer.expires_at

    def subscribe(self, channels: list[int], instance_token: str) -> AudioSubscription:
        if self.counters[audio_forwarding.STATE] == audio_forwarding.FAILED:
            raise RecsError('Audio forwarding worker is unavailable')
        if self.active:
            raise RecsError('This source already has an audio subscriber')
        if (
            not 1 <= len(channels) <= 2
            or len(set(channels)) != len(channels)
            or any(c < 1 or c > self.channels for c in channels)
        ):
            raise RecsError('Select one or two distinct available physical channels')
        if not 0 < self.sample_rate <= 192_000:
            raise RecsError('Audio forwarding supports sample rates up to 192000 Hz')
        if (
            self.counters[audio_forwarding.BLOCK_BYTES]
            > audio_forwarding.MAX_BUFFER_BYTES
            or self.counters[audio_forwarding.BLOCK_FRAMES]
            > self.sample_rate * audio_forwarding.BUFFER_SECONDS
        ):
            raise RecsError(
                'Capture blocks exceed the forwarding byte or latency budget'
            )
        self.generation += 1
        offer = AudioSubscription(
            subscription_id=uuid.uuid4().hex,
            source=self.source,
            clock_id=self.clock_id,
            instance_token=instance_token,
            port=self.listener.getsockname()[1],
            sample_rate=self.sample_rate,
            channels=channels,
            generation=self.generation,
            expires_at=monotonic() + OFFER_SECONDS,
        )
        offer = offer.model_copy(
            update={
                'secret': hmac.digest(
                    self.key, subscription_signature_data(offer), 'sha256'
                ).hex()
            }
        )
        self.subscription = offer
        self.counters[audio_forwarding.DESIRED] = offer.generation
        return offer

    def capture_progressing(self, timeout: float) -> bool:
        observed = self.counters[audio_forwarding.CAPTURE_TIME]
        return (
            self.counters[audio_forwarding.CAPTURE_FRAME] > 0
            and observed > 0
            and 0 <= monotonic_ns() - observed <= timeout * 1_000_000_000
        )

    def unsubscribe(self, subscription_id: str) -> bool:
        if (
            self.subscription is None
            or self.subscription.subscription_id != subscription_id
        ):
            return False
        self.counters[audio_forwarding.DESIRED] = 0
        self.subscription = None
        return True

    def status(self) -> dict[str, object]:
        offer = self.subscription
        connected = (
            self.active
            and offer is not None
            and self.counters[audio_forwarding.ACCEPTED] == offer.generation
            and self.counters[audio_forwarding.STATE] == audio_forwarding.CONNECTED
        )
        return {
            'source': self.source,
            'state': 'failed'
            if self.counters[audio_forwarding.STATE] == audio_forwarding.FAILED
            else 'connected'
            if connected
            else 'pending'
            if self.active
            else 'idle',
            'subscription_id': offer.subscription_id if self.active and offer else None,
            'channels': offer.channels if self.active and offer else [],
            'clock_id': self.clock_id,
            'sample_rate': self.sample_rate,
            'sent_frames': self.counters[audio_forwarding.SENT],
            'dropped_frames': self.counters[audio_forwarding.DROPPED],
            'retained_bytes': self.counters[audio_forwarding.RETAINED],
            'last_send_monotonic_ns': self.counters[audio_forwarding.LAST_SEND],
            'error': {
                0: None,
                1: 'Cannot start forwarding worker',
                2: 'Forwarding resource or protocol failure',
                3: 'Consumer stalled or disconnected',
                4: 'Microphone muted or mic-mute configuration unreadable',
            }.get(self.counters[audio_forwarding.ERROR]),
        }

    def close(self) -> None:
        self.counters[audio_forwarding.DESIRED] = 0
        self.subscription = None
        self.listener.close()
