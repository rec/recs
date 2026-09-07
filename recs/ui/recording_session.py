import hashlib
from pathlib import Path
from time import monotonic_ns

from pydantic import ValidationError
from soundfile import SoundFileError

from recs.base.errors import RecsError
from recs.model.events import KeyEvent
from recs.model.recording import AudioSpan
from recs.model.time import ClockObservation, Position, Rate, Timebase
from recs.recording.events import EventWriter, host_clock_observation
from recs.recording.finalize import finalize_recording
from recs.ui import recording_paths, session_record
from recs.ui.source_recorder import SourceFile


class RecordingSession:
    def __init__(self, session_id: str, started_at: float) -> None:
        self.session_id = session_id
        self.started_at = started_at
        self.continued_from: str | None = None
        self.files_written: set[Path] = set()
        self.finished_files: set[Path] = set()
        self.file_end_frames: dict[Path, int] = {}
        self.file_end_timestamps: dict[Path, float] = {}
        self.file_spans: dict[Path, list[AudioSpan]] = {}
        self.files: dict[Path, session_record.AudioFileRecord] = {}
        self.record_writer: session_record.SessionRecordWriter | None = None
        self.record_errors: list[str] = []
        self.key_writer: EventWriter | None = None
        self.key_ordinal = 0

    def start(self, path: Path, *, enabled: bool) -> None:
        if not enabled:
            return
        self.record_writer = session_record.SessionRecordWriter(
            path,
            started_at=session_record.timestamp_to_json(self.started_at),
            session_id=self.session_id,
            continued_from=self.continued_from,
        )
        self.continued_from = None
        self.write(host_clock_observation())

    def finish(self, timestamp: float) -> None:
        if self.record_writer is None:
            return
        if self.key_writer is not None:
            self.write(self.key_writer.finish())
            self.key_writer = None
        for path in sorted(self.files):
            if path.exists():
                self.record_file_finished(path)
        self.write(host_clock_observation())
        self.write(
            session_record.SessionFooter(
                ended_at=session_record.timestamp_to_json(timestamp),
                duration_seconds=timestamp - self.started_at,
            )
        )
        self.record_writer.close()
        try:
            finalize_recording(self.record_writer.path)
        except (OSError, RecsError, SoundFileError, ValidationError) as error:
            self.record_errors.append(f'Cannot finalize recording: {error}')
        self.record_errors.extend(self.record_writer.take_errors())
        self.record_writer = None

    def record_file_finished(self, path: Path) -> None:
        if path in self.finished_files or path not in self.files:
            return
        file = self.files[path]
        spans = self.file_spans.get(path)
        self.write(
            file.model_copy(
                update={
                    'type': 'file_finished',
                    'timestamp': session_record.timestamp_to_json(
                        recording_paths.timestamp_or_now(
                            self.file_end_timestamps.get(path)
                        )
                    ),
                    'frame_count': self.file_end_frames.get(path),
                    'quantity_count': sum(s.count for s in spans)
                    if spans is not None
                    else None,
                    'audio_spans': spans,
                }
            )
        )
        self.finished_files.add(path)

    def record_file_discarded(self, path: Path) -> None:
        if path in self.files and path not in self.finished_files:
            self.write(self.files[path].model_copy(update={'type': 'file_discarded'}))
            self.finished_files.add(path)

    def reset(
        self,
        started_at: float,
        *,
        session_id: str | None = None,
        continued_from: str | None = None,
    ) -> None:
        if session_id is not None:
            self.session_id = session_id
        self.started_at = started_at
        self.continued_from = continued_from
        self.files_written = set()
        self.finished_files = set()
        self.file_end_frames = {}
        self.file_end_timestamps = {}
        self.file_spans = {}
        self.files = {}

    def record_files(
        self,
        files: list[Path],
        end_frames: dict[Path, int],
        end_timestamps: dict[Path, float],
        spans: dict[Path, list[AudioSpan]],
    ) -> None:
        self.files_written.update(files)
        self.file_end_frames.update(end_frames)
        self.file_end_timestamps.update(end_timestamps)
        self.file_spans.update(spans)

    def record_file_started(self, file: SourceFile, source: str | None) -> None:
        stream_channels = '-'.join(str(c) for c in file.source_channels)
        entry = session_record.AudioFileRecord(
            type='file_started',
            media_type='audio',
            clock_id='clock-'
            + hashlib.sha256(
                (file.capture_id or file.source_name).encode()
            ).hexdigest()[:16],
            timestamp=session_record.timestamp_to_json(
                recording_paths.timestamp_or_now(file.start_timestamp)
            ),
            stream_id=f'audio:{file.source_name}:{stream_channels}'
            + (f':{file.capture_id}' if file.capture_id else ''),
            format=file.path.suffix.removeprefix('.').lower(),
            frame_count=file.start_frame,
            path=file.path.as_posix(),
            source=source or file.source_name,
            track_name=file.track_name,
            source_channels=file.source_channels,
            channels=file.channels,
            sample_rate=file.sample_rate,
            bit_depth=file.bit_depth,
        )
        self.files[file.path] = entry
        self.write(entry)
        if (
            source is None
            and file.start_frame is not None
            and file.start_timestamp is not None
        ):
            clock = Timebase(
                id=entry.clock_id,
                rate=Rate(numerator=file.sample_rate),
            )
            self.write(
                session_record.ClockRecord(
                    timebases=[
                        clock,
                        Timebase(id='wall', rate=Rate(numerator=1_000_000_000)),
                    ],
                    observation=ClockObservation(
                        source=Position(timebase=clock.id, tick=file.start_frame),
                        session=Position(
                            timebase='wall',
                            tick=round(file.start_timestamp * 1_000_000_000),
                        ),
                        timing_source='portaudio_callback_wall',
                        uncertainty_ticks=None,
                    ),
                )
            )

    def write(self, entry: session_record.Record) -> None:
        if self.record_writer is not None:
            if (
                isinstance(entry, session_record.EventRecord)
                and entry.type in {'key_pressed', 'key_released'}
                and entry.key
            ):
                tick = monotonic_ns()
                if self.key_writer is None:
                    self.key_writer = EventWriter(
                        self.record_writer.path.parent / 'key/keyboard.jsonl',
                        'keyboard',
                        'key',
                        Timebase(id='monotonic', rate=Rate(numerator=1_000_000_000)),
                        'host_key_observation',
                        tick,
                    )
                    self.write(self.key_writer.start_entry())
                self.key_writer.write(
                    KeyEvent(
                        tick=tick,
                        ordinal=self.key_ordinal,
                        key=entry.key,
                        action='press' if entry.type == 'key_pressed' else 'release',
                    )
                )
                self.key_ordinal += 1
            if isinstance(entry, session_record.FileRecord):
                path = Path(entry.path)
                entry = entry.model_copy(
                    update={
                        'path': path.resolve()
                        .relative_to(self.record_writer.path.resolve().parent)
                        .as_posix()
                    }
                )
            self.record_writer.write(entry)
            self.record_errors.extend(self.record_writer.take_errors())
