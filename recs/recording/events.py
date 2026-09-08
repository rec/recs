"""Append native events without quantizing their capture clock."""

from pathlib import Path
from time import monotonic_ns, time_ns
from typing import Literal

from ufor.events import StoredEvent
from ufor.time import ClockObservation, Position, Rate, Timebase

from recs.ui.session_record import ClockRecord, EventFileRecord, timestamp_to_json


class EventWriter:
    def __init__(
        self,
        path: Path,
        source: str,
        medium: Literal['midi', 'osc', 'key'],
        timebase: Timebase,
        timing_source: str,
        start_tick: int,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.source = source
        self.medium = medium
        self.timebase = timebase
        self.timing_source = timing_source
        self.start_tick = start_tick
        self.end_tick = start_tick
        self.message_count = 0
        self.previous: tuple[int, int] | None = None
        self.output = path.open('x')

    def start_entry(self) -> EventFileRecord:
        return EventFileRecord(
            type='file_started',
            timestamp=timestamp_to_json(time_ns() / 1_000_000_000),
            stream_id=f'{self.medium}:{self.source}',
            media_type=self.medium,
            format='recs_events',
            path=self.path.as_posix(),
            source=self.source,
            timebase=self.timebase,
            start_tick=self.start_tick,
            timing_source=self.timing_source,
        )

    def write(self, event: StoredEvent) -> None:
        position = event.tick, event.ordinal
        if self.previous is not None and (
            position < self.previous or event.ordinal <= self.previous[1]
        ):
            raise ValueError('Captured event ticks and ordinals must remain ordered')
        self.output.write(event.model_dump_json(exclude_none=True) + '\n')
        self.output.flush()
        self.previous = position
        self.start_tick = min(self.start_tick, event.tick)
        self.end_tick = max(self.end_tick, event.tick + 1)
        self.message_count += 1

    def finish(self) -> EventFileRecord:
        self.output.close()
        return self.start_entry().model_copy(
            update={
                'type': 'file_finished',
                'quantity_count': self.message_count,
                'end_tick': self.end_tick,
            }
        )


def host_clock_observation() -> ClockRecord:
    before = monotonic_ns()
    wall = time_ns()
    after = monotonic_ns()
    return ClockRecord(
        timebases=[
            Timebase(id=i, rate=Rate(numerator=1_000_000_000))
            for i in ('monotonic', 'wall')
        ],
        observation=ClockObservation(
            source=Position(timebase='monotonic', tick=(before + after) // 2),
            session=Position(timebase='wall', tick=wall),
            uncertainty_ticks=(after - before + 1) // 2,
            timing_source='host_clock_pair',
        ),
    )
