"""Standard MIDI Files are an explicit, quantized interchange export."""

from fractions import Fraction
from pathlib import Path
from typing import Annotated

import mido
import tyro
from pydantic import BaseModel
from ufor.events import MidiEvent
from ufor.recording import EventStream

from recs.base.errors import RecsError
from recs.recording.files import sealed_asset, verify_events
from recs.recording.read import read_recording_chain


class ExportMidi(BaseModel, frozen=True):
    recording: Annotated[Path, tyro.conf.Positional]
    source: Annotated[str, tyro.conf.Positional]
    destination: Annotated[Path, tyro.conf.Positional]


def export_midi(recording: Path, source: str, destination: Path) -> Path:
    events: list[MidiEvent] = []
    origins: list[int] = []
    rates: set[Fraction] = set()
    clocks: set[str] = set()
    for path, document in read_recording_chain(recording):
        for stream in document.body.streams:
            if not isinstance(stream, EventStream) or stream.source_id != source:
                continue
            if document.body.state != 'sealed' or stream.event_kind != 'midi':
                raise RecsError('MIDI export requires sealed native MIDI streams')
            clock = next(t for t in document.timebases if t.id == stream.timebase)
            clocks.add(clock.id)
            rates.add(Fraction(clock.rate.numerator, clock.rate.denominator))
            assets = {a.id: a for a in document.assets}
            paths: dict[str, Path] = {}
            for fragment in stream.fragments:
                asset = assets[fragment.asset]
                payload = path.parent / asset.path
                actual = sealed_asset(payload, path.parent, asset.id, asset.encoding)
                if actual != asset:
                    raise RecsError(f'MIDI asset differs from recording: {payload}')
                paths[asset.id] = payload
                assert fragment.start is not None
                origins.append(fragment.start)
            verify_events(stream, paths)
            for fragment in stream.fragments:
                with paths[fragment.asset].open() as lines:
                    events.extend(MidiEvent.model_validate_json(e) for e in lines)
    if len(clocks) != 1 or len(rates) != 1 or not origins:
        raise RecsError(f'Expected one native MIDI clock for source {source}')
    events.sort(key=lambda e: (e.tick, e.ordinal))
    if len({e.ordinal for e in events}) != len(events):
        raise RecsError('MIDI continuation repeats event ordinals')
    origin, rate = min(origins), next(iter(rates))
    midi = mido.MidiFile(type=0, ticks_per_beat=960)
    track = mido.MidiTrack([mido.MetaMessage('set_tempo', tempo=500000)])
    midi.tracks.append(track)
    previous = 0
    for event in events:
        tick = round(Fraction((event.tick - origin) * 1920) / rate)
        message = mido.Message.from_bytes(event.data)
        if message.is_realtime:
            raise RecsError(
                f'Standard MIDI Files cannot represent {message.type} messages; '
                'the native recording retains them'
            )
        message.time = tick - previous
        track.append(message)
        previous = tick
    with destination.open('xb') as target:
        midi.save(file=target)
    return destination


def main(argv: list[str] | None = None) -> int:
    config = tyro.cli(ExportMidi, args=argv, prog='recs session export-midi')
    print(export_midi(config.recording, config.source, config.destination))
    return 0
