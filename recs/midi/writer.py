from pathlib import Path
from typing import Protocol

from recs.base import times
from recs.base.types import MidiTiming
from recs.misc import legal_filename
from recs.ui.session_manifest import ManifestFile, timestamp_to_json

TICKS_PER_BEAT = 960
TEMPO = 500_000
TICKS_PER_SECOND = TICKS_PER_BEAT * 1_000_000 / TEMPO


class MidiMessage(Protocol):
    time: object

    def copy(self, **kwargs: object) -> object:
        pass


class MidiWriter:
    def __init__(
        self,
        session_directory: Path,
        port_name: str,
        timing_source: MidiTiming,
    ) -> None:
        import mido

        self.session_directory = session_directory
        self.port_name = port_name
        self.timing_source = timing_source
        self.message_count = 0
        self.last_timestamp: float | None = None
        self.last_tick = 0
        self.path = _next_path(session_directory, port_name)
        self.file = mido.MidiFile(type=0, ticks_per_beat=TICKS_PER_BEAT)
        self.track = mido.MidiTrack()
        self.file.tracks.append(self.track)
        self.track.append(mido.MetaMessage('set_tempo', tempo=TEMPO, time=0))
        self.track.append(mido.MetaMessage('track_name', name=port_name, time=0))

    def record(self, message: MidiMessage, timestamp: float | None = None) -> None:
        delta = self._delta_seconds(message, timestamp)
        self.track.append(message.copy(time=round(delta * TICKS_PER_SECOND)))
        self.message_count += 1

    def finish(self) -> ManifestFile:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file.save(self.path)
        return ManifestFile(
            type='file_finished',
            kind='midi',
            timestamp=timestamp_to_json(times.timestamp()),
            path=self.path.as_posix(),
            source=self.port_name,
            message_count=self.message_count,
            timing_source=str(self.timing_source),
            midi_port=self.port_name,
        )

    def _delta_seconds(self, message: MidiMessage, timestamp: float | None) -> float:
        if self.timing_source == MidiTiming.mido:
            value = float(getattr(message, 'time', 0.0) or 0.0)
            return max(value, 0.0)
        now = times.timestamp() if timestamp is None else timestamp
        if self.last_timestamp is None:
            self.last_timestamp = now
            return 0.0
        delta = now - self.last_timestamp
        self.last_timestamp = now
        return max(delta, 0.0)


def _next_path(session_directory: Path, port_name: str) -> Path:
    stem = legal_filename.legal_filename(port_name)
    path = session_directory / f'{stem}.mid'
    index = 2
    while path.exists():
        path = session_directory / f'{stem}-{index}.mid'
        index += 1
    return path
