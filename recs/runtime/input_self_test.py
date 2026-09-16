import argparse
from pathlib import Path

import numpy as np
import soundfile
from pydantic import BaseModel, Field

from recs.cfg.cfg import Cfg

from .recorder import Recorder


class DiagnosticFile(BaseModel):
    path: str
    channels: int
    sample_rate: int
    peak: float
    rms: float
    channel_peaks: list[float] = Field(default_factory=list)
    channel_rms: list[float] = Field(default_factory=list)


class DiagnosticTrack(BaseModel):
    name: str
    channels: list[int]


class DiagnosticDevice(BaseModel):
    name: str
    channels: int
    sample_rate: int
    tracks: list[DiagnosticTrack] = Field(default_factory=list)


class DiagnosticBuffer(BaseModel):
    source: str
    dropped_blocks: int = 0
    dropped_frames: int = 0
    max_queued_seconds: float = 0.0
    max_write_seconds: float = 0.0


class DiagnosticReport(BaseModel):
    devices: list[DiagnosticDevice] = Field(default_factory=list)
    files: list[DiagnosticFile] = Field(default_factory=list)
    buffers: list[DiagnosticBuffer] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    cfg = Cfg(
        include=args.include,
        output_directory=args.output,
        quiet_after_end=0,
        quiet_before_start=0,
        record_everything=True,
        shortest_file_time=0,
        silent=True,
        total_run_time=args.seconds,
    )
    recorder = Recorder(cfg)
    recorder.run()
    print(_report(recorder).model_dump_json(indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='recs test-input')
    parser.add_argument('--include', action='append', default=[])
    parser.add_argument('--seconds', type=float, default=5.0)
    parser.add_argument('--output', default='recs-self-test')
    return parser


def _report(recorder: Recorder) -> DiagnosticReport:
    report = DiagnosticReport(
        devices=_device_reports(recorder),
        buffers=_buffer_reports(recorder),
        warnings=recorder.error_messages(),
    )
    for path in sorted(p for p in recorder.session.files_written if p.exists()):
        try:
            data, sample_rate = soundfile.read(path, always_2d=True)
        except (OSError, RuntimeError) as e:
            report.errors.append(f'{path}: {e}')
            continue
        report.files.append(_file_report(path, data, sample_rate))
    return report


def _file_report(path: Path, data: np.ndarray, sample_rate: int) -> DiagnosticFile:
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0
    channel_peaks = [
        float(np.max(np.abs(data[:, i]))) if data.size else 0.0
        for i in range(data.shape[1])
    ]
    channel_rms = [
        float(np.sqrt(np.mean(np.square(data[:, i])))) if data.size else 0.0
        for i in range(data.shape[1])
    ]
    return DiagnosticFile(
        path=path.as_posix(),
        channels=data.shape[1],
        sample_rate=sample_rate,
        peak=peak,
        rms=rms,
        channel_peaks=channel_peaks,
        channel_rms=channel_rms,
    )


def _device_reports(recorder: Recorder) -> list[DiagnosticDevice]:
    devices = getattr(recorder, '_devices', None)
    sources = getattr(devices, 'sources', {})
    return [
        DiagnosticDevice(
            name=source.name,
            channels=source.source.channels,
            sample_rate=source.source.samplerate,
            tracks=[
                DiagnosticTrack(name=track.name, channels=list(track.channels))
                for track in source.tracks
            ],
        )
        for source in sources.values()
    ]


def _buffer_reports(recorder: Recorder) -> list[DiagnosticBuffer]:
    devices = getattr(recorder, '_devices', None)
    stats = getattr(devices, 'buffer_stats', {})
    return [
        DiagnosticBuffer(
            source=source,
            dropped_blocks=buffer.dropped_blocks,
            dropped_frames=buffer.dropped_frames,
            max_queued_seconds=buffer.max_queued_seconds,
            max_write_seconds=buffer.max_write_seconds,
        )
        for source, buffer in sorted(stats.items())
    ]
