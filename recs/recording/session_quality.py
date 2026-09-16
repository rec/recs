"""Explain recorded quality evidence without changing a session or its media."""

from enum import StrEnum, auto
from pathlib import Path
from typing import Annotated

import soundfile
import tyro
from pydantic import BaseModel, Field
from ufor.recording import AudioFragment, AudioStream, GapReason

from ..base.errors import RecsError
from . import audio_quality, legacy, session_record
from .read import read_recording


class QualityCli(BaseModel, frozen=True):
    """Report one recording document's evidence; audio decoding is opt-in.

    Frame positions are source-local, half-open ranges, not cross-device alignment.
    Near-full-scale advisories are not proof of clipping. No quietness verdicts.
    """

    path: Annotated[Path, tyro.conf.Positional]
    json_output: Annotated[bool, tyro.conf.arg(name='json')] = False
    analyze_audio: bool = False
    analysis: audio_quality.AnalysisSettings = Field(
        default_factory=audio_quality.AnalysisSettings
    )


class Severity(StrEnum):
    info = auto()
    advisory = auto()
    warning = auto()
    error = auto()


class Finding(BaseModel, frozen=True):
    severity: Severity
    kind: str
    evidence: str
    source_id: str | None = None
    stream: str | None = None
    timebase: str | None = None
    start_frame: int | None = None
    end_frame: int | None = None


class TrackQuality(BaseModel, frozen=True):
    source_id: str
    source_name: str | None
    stream: str
    track_name: str | None
    timebase: str
    sample_rate: float
    captured_frames: int
    captured_seconds: float
    unresolved_frames: int
    gap_frames: dict[str, int]
    audio: list[audio_quality.AudioMeasurement] = Field(default_factory=list)


class QualityReport(BaseModel, frozen=True):
    path: str
    analysis: audio_quality.AnalysisSettings | None
    tracks: list[TrackQuality] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    limitations: list[str] = Field(
        default_factory=lambda: [
            'One recording document only; continuation documents are not followed.',
            'Frame ranges are half-open on the named source timebase; '
            'independent clocks are not aligned.',
            'Unmapped audio has asset positions only; '
            'journal intervals do not locate its samples.',
            'Metadata is evidence, not verified media integrity. '
            'Use recs record check for full verification.',
            'Optional analysis measures a prefix of each fragment. '
            'Peak and RMS are normalized linear amplitudes (1 = full scale).',
            'Run ranges stop at fragment/analysis boundaries; '
            'they do not establish where unexamined audio stops being near full scale.',
            'Near-full-scale runs are advisories, not proof of clipping; '
            'low signal levels receive no verdict.',
        ]
    )


def inspect(
    path: Path, analysis: audio_quality.AnalysisSettings | None = None
) -> QualityReport:
    record_path = path / 'recording.toml' if path.is_dir() else path
    findings: list[Finding] = []
    tracks: list[TrackQuality] = []
    try:
        document = read_recording(record_path)
    except (RecsError, ValueError) as error:
        return QualityReport(
            path=str(record_path),
            analysis=analysis,
            findings=[
                Finding(
                    severity=Severity.error,
                    kind='unreadable_recording',
                    evidence=str(error),
                ),
            ],
        )
    body = document.body
    assets = {a.name: a for a in document.assets}
    clocks = {t.name: t.rate.numerator / t.rate.denominator for t in document.timebases}
    if body.state != 'sealed':
        findings.append(
            Finding(
                severity=Severity.warning,
                kind='open_recording',
                evidence='body.state = open',
            )
        )
    for index, unfinished in enumerate(body.unfinished_files):
        findings.append(
            Finding(
                severity=Severity.warning,
                kind='unfinished_file',
                source_id=unfinished.source_id,
                evidence=f'body.unfinished_files[{index}]: {unfinished.journal_path}',
            )
        )
    for stream in body.streams:
        if not isinstance(stream, AudioStream):
            continue
        context = dict(
            source_id=stream.source_id,
            stream=stream.name,
            timebase=stream.stream.timebase,
        )
        prefix = f'body.streams[{stream.name}]'
        gaps: dict[str, int] = {}
        for index, gap in enumerate(stream.gaps):
            gaps[gap.reason] = gaps.get(gap.reason, 0) + gap.end - gap.start
            findings.append(
                Finding(
                    severity=Severity.info
                    if gap.reason
                    in (GapReason.silence_suppressed, GapReason.short_capture)
                    else Severity.warning,
                    kind=gap.reason,
                    evidence=f'{prefix}.gaps[{index}]',
                    start_frame=gap.start,
                    end_frame=gap.end,
                    **context,
                )
            )
        for index, fragment in enumerate(stream.unmapped_fragments):
            findings.append(
                Finding(
                    severity=Severity.warning,
                    kind='unresolved_placement',
                    evidence=(
                        f'{prefix}.unmapped_fragments[{index}]: '
                        f'{fragment.asset}, {fragment.count} frames; {fragment.reason}'
                    ),
                    **context,
                )
            )
        # Encoding variants describe the same captured interval, not extra time.
        captured = sum(
            e - s
            for s, e in sorted({(f.start, f.start + f.count) for f in stream.fragments})
        )
        measurements: list[audio_quality.AudioMeasurement] = []
        if analysis is not None:
            for fragment in [*stream.fragments, *stream.unmapped_fragments]:
                asset = assets[fragment.asset]
                try:
                    media = (record_path.parent / asset.path).resolve()
                    if not media.is_relative_to(record_path.parent.resolve()):
                        raise RecsError('Asset escapes the session directory')
                    measurement = audio_quality.measure(
                        media,
                        asset.name,
                        fragment.asset_start
                        if isinstance(fragment, AudioFragment)
                        else 0,
                        fragment.start if isinstance(fragment, AudioFragment) else None,
                        fragment.count,
                        stream.stream.channels,
                        clocks[stream.stream.timebase],
                        analysis,
                    )
                    measurements.append(measurement)
                    if any(c.near_full_scale_frames for c in measurement.channels):
                        findings.append(
                            Finding(
                                severity=Severity.advisory,
                                kind='near_full_scale',
                                evidence=f'{asset.path}: see channel measurements '
                                'and exact run ranges',
                                **context,
                            )
                        )
                except (
                    OSError,
                    ValueError,
                    RecsError,
                    soundfile.SoundFileError,
                ) as error:
                    findings.append(
                        Finding(
                            severity=Severity.error,
                            kind='audio_analysis_failed',
                            evidence=f'{asset.path}: {error}',
                            **context,
                        )
                    )
        tracks.append(
            TrackQuality(
                **context,
                source_name=stream.source_name,
                track_name=stream.track_name,
                sample_rate=clocks[stream.stream.timebase],
                captured_frames=captured,
                captured_seconds=captured / clocks[stream.stream.timebase],
                unresolved_frames=sum(f.count for f in stream.unmapped_fragments),
                gap_frames=gaps,
                audio=measurements,
            )
        )
    if body.journal is not None:
        asset = assets[body.journal]
        try:
            journal_path = (record_path.parent / asset.path).resolve()
            if not journal_path.is_relative_to(record_path.parent.resolve()):
                raise RecsError('Journal escapes the session directory')
            journal = (
                legacy.read(journal_path)
                if asset.encoding == 'recs-session-v3'
                else session_record.read(journal_path)
            )
            for message in journal.warnings + journal.errors:
                findings.append(
                    Finding(
                        severity=Severity.warning,
                        kind='journal_diagnostic',
                        evidence=f'{asset.path}: {message}',
                    )
                )
            for index, event in enumerate(journal.events):
                if event.type in (
                    'buffer_overflow',
                    'source_failed',
                    'source_stopped',
                    'source_offline',
                    'midi_source_failed',
                    'midi_source_stopped',
                ):
                    findings.append(
                        Finding(
                            severity=Severity.warning,
                            kind=event.type,
                            evidence=f'{asset.path}: events[{index}]: '
                            f'{event.model_dump_json(exclude_none=True)}',
                        )
                    )
        except (OSError, RecsError, ValueError) as error:
            findings.append(
                Finding(
                    severity=Severity.error,
                    kind='unreadable_journal',
                    evidence=f'{asset.path}: {error}',
                )
            )
    return QualityReport(
        path=str(record_path), analysis=analysis, tracks=tracks, findings=findings
    )


def main(argv: list[str]) -> int:
    command = tyro.cli(QualityCli, args=argv, prog='recs session quality')
    report = inspect(command.path, command.analysis if command.analyze_audio else None)
    if command.json_output:
        print(report.model_dump_json(indent=2))
    else:
        print(f'Session quality: {report.path}')
        settings = (
            report.analysis.model_dump_json() if report.analysis else 'metadata only'
        )
        print(f'Analysis settings: {settings}')
        for track in report.tracks:
            print(
                f'{track.source_id} / {track.track_name or track.stream}: '
                f'{track.captured_frames} mapped captured frames '
                f'({track.captured_seconds:g} s), timebase={track.timebase}, '
                f'rate={track.sample_rate:g} Hz; '
                f'{track.unresolved_frames} unresolved frames'
            )
            for measurement in track.audio:
                print(measurement.model_dump_json(indent=2))
        for finding in report.findings:
            location = f'{finding.stream or finding.source_id or "session"}'
            if finding.start_frame is not None:
                location += (
                    f' [{finding.start_frame}, {finding.end_frame}) frames, '
                    f'timebase={finding.timebase}'
                )
            print(
                f'{finding.severity.upper()} {finding.kind}: '
                f'{location}: {finding.evidence}'
            )
        for limitation in report.limitations:
            print(f'NOTE: {limitation}')
    return int(any(f.severity == Severity.error for f in report.findings))
