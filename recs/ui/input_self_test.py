import argparse
from pathlib import Path

import numpy as np
import soundfile
from pydantic import BaseModel, Field

from recs.cfg import Cfg

from .recorder import Recorder


class DiagnosticFile(BaseModel):
    path: str
    channels: int
    sample_rate: int
    peak: float
    rms: float


class DiagnosticReport(BaseModel):
    files: list[DiagnosticFile] = Field(default_factory=list)
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
    report = DiagnosticReport(warnings=recorder.warnings)
    for path in sorted(p for p in recorder.files_written if p.exists()):
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
    return DiagnosticFile(
        path=path.as_posix(),
        channels=data.shape[1],
        sample_rate=sample_rate,
        peak=peak,
        rms=rms,
    )
