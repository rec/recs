from pathlib import Path

from recs.ui import recording_paths, session_record
from recs.ui.source_recorder import SourceFile


class RecordingSession:
    def __init__(self, session_id: str, started_at: float) -> None:
        self.session_id = session_id
        self.started_at = started_at
        self.continued_from: str | None = None
        self.files_written: set[Path] = set()
        self.file_end_frames: dict[Path, int] = {}
        self.file_end_timestamps: dict[Path, float] = {}
        self.files: dict[Path, session_record.FileEntry] = {}
        self.record_writer: session_record.SessionRecordWriter | None = None
        self.record_errors: list[str] = []

    def start(self, path: Path, *, dry_run: bool, silence_preview: bool) -> None:
        if dry_run or silence_preview:
            return
        self.record_writer = session_record.SessionRecordWriter(
            path,
            started_at=session_record.timestamp_to_json(self.started_at),
            session_id=self.session_id,
            continued_from=self.continued_from,
        )
        self.continued_from = None

    def finish(self, timestamp: float) -> None:
        if self.record_writer is None:
            return
        for path, file in sorted(self.files.items()):
            if path.exists():
                end_frame = self.file_end_frames.get(path)
                self.write(
                    file.model_copy(
                        update={
                            'type': 'file_finished',
                            'timestamp': session_record.timestamp_to_json(
                                recording_paths.timestamp_or_now(
                                    self.file_end_timestamps.get(path)
                                )
                            ),
                            'frame_count': end_frame,
                            'quantity_count': (
                                end_frame - file.frame_count
                                if end_frame is not None
                                and file.frame_count is not None
                                else None
                            ),
                        }
                    )
                )
        self.write(
            session_record.FooterEntry(
                ended_at=session_record.timestamp_to_json(timestamp),
                duration_seconds=timestamp - self.started_at,
            )
        )
        self.record_writer.close()
        self.record_errors.extend(self.record_writer.take_errors())
        self.record_writer = None

    def reset(self, started_at: float) -> None:
        self.started_at = started_at
        self.files_written = set()
        self.file_end_frames = {}
        self.file_end_timestamps = {}
        self.files = {}

    def record_files(
        self,
        files: list[Path],
        end_frames: dict[Path, int],
        end_timestamps: dict[Path, float],
    ) -> None:
        self.files_written.update(files)
        self.file_end_frames.update(end_frames)
        self.file_end_timestamps.update(end_timestamps)

    def record_file_started(self, file: SourceFile, source: str | None) -> None:
        entry = session_record.FileEntry(
            type='file_started',
            media_type='audio',
            timestamp=session_record.timestamp_to_json(
                recording_paths.timestamp_or_now(file.start_timestamp)
            ),
            stream_id=f'audio:{source or "unknown"}:{file.track}',
            format=file.path.suffix.removeprefix('.').lower(),
            frame_count=file.start_frame,
            path=file.path.as_posix(),
            source=source,
            track=file.track,
            channels=file.channels,
            sample_rate=file.sample_rate,
            bit_depth=file.bit_depth,
        )
        self.files[file.path] = entry
        self.write(entry)

    def write(self, entry: session_record.RecordEntry) -> None:
        if self.record_writer is not None:
            if isinstance(entry, session_record.FileEntry):
                path = Path(entry.path)
                if path.is_absolute():
                    entry = entry.model_copy(
                        update={
                            'path': path.relative_to(
                                self.record_writer.path.parent
                            ).as_posix()
                        }
                    )
            self.record_writer.write(entry)
            self.record_errors.extend(self.record_writer.take_errors())
