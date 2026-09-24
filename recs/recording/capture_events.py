import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple
from weakref import WeakSet

from ufor.recording import AudioSpan, Gap, GapReason

from recs.audio.channel_writer import ChannelWriter
from recs.cfg.track_names import track_name
from recs.recording import session_record
from recs.recording.session_record import AudioTimelineRecord


class SourceFile(NamedTuple):
    path: Path
    source_name: str
    track_name: str
    source_channels: list[int]
    channels: int
    sample_rate: int
    bit_depth: int
    start_frame: int | None = None
    start_timestamp: float | None = None
    capture_id: str | None = None


class SourceFileEvents:
    def __init__(
        self, writers: Sequence['ChannelWriter'], capture_id: str | None = None
    ) -> None:
        self.capture_id = capture_id
        self.file_counts = [0] * len(writers)
        self.pending_file_end_frames: dict[Path, int] = {}
        self.pending_file_end_timestamps: dict[Path, float] = {}
        self.pending_file_spans: dict[Path, list[AudioSpan]] = {}
        self.pending_timelines: list[AudioTimelineRecord] = []
        self.timeline_writers: WeakSet[ChannelWriter] = WeakSet()
        self.pending_finished: set[Path] = set()
        self.pending_discarded: set[Path] = set()

    def reset_writers(self, writers: Sequence['ChannelWriter']) -> None:
        self.file_counts = [0] * len(writers)

    def remember_finished_files(self, writers: Sequence['ChannelWriter']) -> None:
        for writer in writers:
            self.pending_file_end_frames.update(writer.file_end_frames)
            self.pending_file_end_timestamps.update(writer.file_end_timestamps)
            self.pending_file_spans.update(writer.file_spans)
            self.pending_finished.update(writer.finished_files)
            self.pending_discarded.update(writer.discarded_files)
            if writer.observed_ranges and writer not in self.timeline_writers:
                self.pending_timelines.append(audio_timeline(writer, self.capture_id))
                self.timeline_writers.add(writer)

    def timelines(self) -> list[AudioTimelineRecord]:
        result, self.pending_timelines = self.pending_timelines, []
        return result

    def discarded(self, writers: Sequence[ChannelWriter]) -> list[Path]:
        result = self.pending_discarded | {
            p for w in writers for p in w.discarded_files
        }
        self.pending_discarded = set()
        for writer in writers:
            writer.discarded_files.clear()
        return sorted(result)

    def finished(self, writers: Sequence[ChannelWriter]) -> list[Path]:
        result = self.pending_finished | {p for w in writers for p in w.finished_files}
        self.pending_finished = set()
        for writer in writers:
            writer.finished_files.clear()
        return sorted(result)

    def new_files(
        self, writers: Sequence['ChannelWriter'], bit_depth: int
    ) -> tuple[list[Path], list[SourceFile]]:
        result: list[Path] = []
        records: list[SourceFile] = []
        for index, writer in enumerate(writers):
            self.file_counts[index] = min(
                self.file_counts[index], len(writer.files_written)
            )
            new_files = writer.files_written[self.file_counts[index] :]
            result.extend(new_files)
            records.extend(
                SourceFile(
                    path=path,
                    source_name=writer.track.source.name,
                    track_name=(
                        track_name(writer.track_names, writer.track)
                        or writer.track.name
                    ),
                    source_channels=list(writer.track.channels),
                    channels=len(writer.track.channels),
                    sample_rate=writer.track.source.samplerate,
                    bit_depth=bit_depth,
                    start_frame=writer.file_start_frames[path],
                    start_timestamp=writer.file_start_timestamps[path],
                    capture_id=self.capture_id,
                )
                for path in new_files
            )
            self.file_counts[index] = len(writer.files_written)
        return result, records

    def end_frames(self, writers: Sequence['ChannelWriter']) -> dict[Path, int]:
        result = self.pending_file_end_frames | {
            p: frame for w in writers for p, frame in w.file_end_frames.items()
        }
        self.pending_file_end_frames = {}
        return result

    def spans(self, writers: Sequence['ChannelWriter']) -> dict[Path, list[AudioSpan]]:
        result = self.pending_file_spans | {
            p: list(s) for w in writers for p, s in w.file_spans.items()
        }
        self.pending_file_spans = {}
        return result

    def end_timestamps(self, writers: Sequence['ChannelWriter']) -> dict[Path, float]:
        result = self.pending_file_end_timestamps | {
            p: timestamp
            for w in writers
            for p, timestamp in w.file_end_timestamps.items()
        }
        self.pending_file_end_timestamps = {}
        return result


def capture_clock_id(identity: str) -> str:
    return 'clock-' + hashlib.sha256(identity.encode()).hexdigest()[:16]


def audio_timeline(
    writer: ChannelWriter, capture_id: str | None = None
) -> AudioTimelineRecord:
    observed = writer.observed_ranges
    captured = [s for v in writer.file_spans.values() for s in v]
    discarded = writer.discarded_spans
    boundaries = sorted(
        {
            *(p for r in observed for p in (r.start, r.end)),
            *(p for s in captured for p in (s.start, s.start + s.count)),
            *(p for s in discarded for p in (s.start, s.start + s.count)),
        }
    )
    gaps: list[Gap] = []
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        if any(s.start <= start < s.start + s.count for s in captured):
            continue
        reason = (
            GapReason.silence_suppressed
            if any(r.start <= start < r.end for r in observed)
            else GapReason.input_overflow
        )
        if any(s.start <= start < s.start + s.count for s in discarded):
            reason = GapReason.short_capture
        if gaps and gaps[-1].end == start and gaps[-1].reason == reason:
            gaps[-1] = Gap(start=gaps[-1].start, end=end, reason=reason)
        else:
            gaps.append(Gap(start=start, end=end, reason=reason))
    name = track_name(writer.track_names, writer.track) or writer.track.name
    return AudioTimelineRecord(
        clock_id=capture_clock_id(capture_id or writer.track.source.name),
        stream_id=session_record.audio_stream_id(
            writer.track.source.name, name, capture_id
        ),
        sample_rate=writer.track.source.samplerate,
        source_channels=list(writer.track.channels),
        start=observed[0].start,
        end=writer.timeline_frame,
        gaps=gaps,
    )
