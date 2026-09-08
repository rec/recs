import hashlib
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from time import monotonic_ns
from typing import Protocol

from ufor.events import MidiEvent
from ufor.time import ClockObservation, Position, Rate, Timebase

from recs.base.types import MidiTiming
from recs.misc import legal_filename
from recs.recording.events import EventWriter
from recs.ui.session_record import ClockRecord


class MidiMessage(Protocol):
    time: object

    def bytes(self) -> list[int]:
        pass


class MidiClock:
    def __init__(self, timing_source: MidiTiming, start_tick: int) -> None:
        self.timing_source = timing_source
        self.start_tick = start_tick
        self.elapsed = Fraction(0)
        self.ordinal = 0
        self.last_tick = start_tick
        self.received_tick = start_tick

    def capture(self, message: MidiMessage, received_tick: int) -> MidiEvent:
        delta = Fraction(str(message.time or 0))
        if delta < 0:
            raise ValueError('MIDI source delta cannot be negative')
        self.elapsed += delta
        tick = (
            self.start_tick + round(self.elapsed * 1_000_000_000)
            if self.timing_source == MidiTiming.mido
            else received_tick
        )
        if tick < self.last_tick:
            raise ValueError('MIDI capture clock moved backwards')
        event = MidiEvent(tick=tick, ordinal=self.ordinal, data=message.bytes())
        self.last_tick = tick
        self.received_tick = received_tick
        self.ordinal += 1
        return event


class MidiWriter(EventWriter):
    def __init__(
        self,
        session_directory: Path,
        port_name: str,
        timing_source: MidiTiming,
        started_at: float,
        clock: MidiClock | None = None,
    ) -> None:
        self.clock = clock or MidiClock(timing_source, monotonic_ns())
        super().__init__(
            _next_path(session_directory, port_name, started_at),
            port_name,
            'midi',
            Timebase(
                id='clock-'
                + hashlib.sha256(('midi:' + port_name).encode()).hexdigest()[:16],
                rate=Rate(numerator=1_000_000_000),
            ),
            str(timing_source),
            self.clock.last_tick,
        )

    def record(self, message: MidiMessage, received_tick: int | None = None) -> None:
        self.write(
            self.clock.capture(
                message, monotonic_ns() if received_tick is None else received_tick
            )
        )

    def clock_entry(self) -> ClockRecord:
        return ClockRecord(
            timebases=[
                self.timebase,
                Timebase(id='monotonic', rate=Rate(numerator=1_000_000_000)),
            ],
            observation=ClockObservation(
                source=Position(timebase=self.timebase.id, tick=self.clock.last_tick),
                session=Position(timebase='monotonic', tick=self.clock.received_tick),
                timing_source='midi_'
                + str(self.clock.timing_source)
                + '_observed_at_callback',
                uncertainty_ticks=0
                if self.clock.timing_source == MidiTiming.system
                else None,
            ),
        )


def _next_path(session_directory: Path, port_name: str, started_at: float) -> Path:
    stem = legal_filename.legal_filename(port_name)
    stamp = datetime.fromtimestamp(started_at).strftime('%Y%m%d-%H%M%S')
    path = session_directory / f'{stem}-{stamp}.jsonl'
    index = 2
    while path.exists():
        path = session_directory / f'{stem}-{stamp}-{index}.jsonl'
        index += 1
    return path
