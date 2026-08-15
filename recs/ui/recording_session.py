from pathlib import Path

from recs.ui import recording_paths, session_manifest
from recs.ui.source_recorder import SourceFile


class RecordingSession:
    def __init__(self, session_id: str, started_at: float) -> None:
        self.session_id = session_id
        self.started_at = started_at
        self.continued_from: str | None = None
        self.files_written: set[Path] = set()
        self.file_end_frames: dict[Path, int] = {}
        self.file_end_timestamps: dict[Path, float] = {}
        self.files: dict[Path, session_manifest.ManifestFile] = {}
        self.manifest: session_manifest.SessionManifestWriter | None = None

    def start(self, path: Path, *, dry_run: bool, silence_preview: bool) -> None:
        if dry_run or silence_preview:
            return
        self.manifest = session_manifest.SessionManifestWriter(
            path,
            started_at=session_manifest.timestamp_to_json(self.started_at),
            session_id=self.session_id,
            continued_from=self.continued_from,
        )
        self.continued_from = None

    def finish(self, timestamp: float) -> None:
        if self.manifest is None:
            return
        for path, file in sorted(self.files.items()):
            if path.exists():
                self.write(
                    file.model_copy(
                        update={
                            'type': 'file_finished',
                            'timestamp': session_manifest.timestamp_to_json(
                                recording_paths.timestamp_or_now(
                                    self.file_end_timestamps.get(path)
                                )
                            ),
                            'frame_count': self.file_end_frames.get(path),
                        }
                    )
                )
        self.write(
            session_manifest.ManifestFooter(
                ended_at=session_manifest.timestamp_to_json(timestamp),
                duration=timestamp - self.started_at,
            )
        )
        self.manifest.close()
        self.manifest = None

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
        record = session_manifest.ManifestFile(
            type='file_started',
            timestamp=session_manifest.timestamp_to_json(
                recording_paths.timestamp_or_now(file.start_timestamp)
            ),
            frame_count=file.start_frame,
            path=file.path.as_posix(),
            source=source,
            track=file.track,
            channels=file.channels,
            sample_rate=file.sample_rate,
            bit_depth=file.bit_depth,
        )
        self.files[file.path] = record
        self.write(record)

    def write(self, record: session_manifest.ManifestRecord) -> None:
        if self.manifest is not None:
            self.manifest.write(record)
