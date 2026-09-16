"""Resolve numbered marker anchors into an ordinary source-local audio edit."""

import os
from fractions import Fraction
from pathlib import Path
from typing import Annotated

import tyro
from pydantic import BaseModel, Field
from ufor import arrangement, interface
from ufor.encoding import Format, Subtype
from ufor.recording import AudioStream, RecordingScore
from ufor.streams import AudioType, FileDestination
from ufor.time import Rate, Timebase

from ..base.errors import RecsError
from ..recording.markers import Marker, read_markers
from ..recording.read import read_recording
from ..recording.session_record import MarkerPosition
from .session import execute_edit


class ExtractCli(BaseModel, frozen=True):
    """Preview marker extraction; supply --destination to render a new session.

    Use numbers from session markers, not labels. Select one capture clock.
    Without --end-marker, lead/tail surround --start-marker. Durations are seconds.
    Historical unpositioned markers are rejected, never mapped from wall time.
    """

    path: Annotated[Path, tyro.conf.Positional]
    clock: str
    start_marker: int = Field(ge=1)
    end_marker: int | None = Field(default=None, ge=1)
    lead: float = Field(default=0, ge=0, allow_inf_nan=False)
    tail: float = Field(default=0, ge=0, allow_inf_nan=False)
    tracks: list[str] = Field(default_factory=list)
    """Exact stream IDs on the selected clock; default: all its audio streams."""
    destination: Path | None = None
    json_output: Annotated[bool, tyro.conf.arg(name='json')] = False


class ExtractionPlan(BaseModel, frozen=True):
    recording: Path
    clock: str
    sample_rate: int
    markers: list[Marker]
    tracks: list[str]
    requested_start_frame: int
    requested_end_frame: int
    start_frame: int
    end_frame: int


def plan_extraction(
    command: ExtractCli,
) -> tuple[ExtractionPlan, arrangement.ArrangementScore]:
    path = command.path / 'recording.toml' if command.path.is_dir() else command.path
    path = path.resolve()
    document = read_recording(path)
    if document.body.state != 'sealed':
        raise RecsError('Marker extraction requires a sealed recording')
    markers = read_markers(path, document)
    numbers = [command.start_marker, command.end_marker or command.start_marker]
    if any(n > len(markers) for n in numbers):
        raise RecsError('Marker number does not exist; use recs session markers')
    selected = [markers[n - 1] for n in numbers]
    positions = [_position(m, command.clock) for m in selected]
    clocks = [t for t in document.timebases if t.name == command.clock]
    if not clocks or clocks[0].rate.denominator != 1:
        raise RecsError('Selected clock must be an integer-rate audio clock')
    rate = clocks[0].rate.numerator
    if any(p.sample_rate != rate for p in positions):
        raise RecsError('Marker sample rate disagrees with the selected clock')
    streams = [
        s
        for s in document.body.streams
        if isinstance(s, AudioStream)
        and s.stream.timebase == command.clock
        and (not command.tracks or s.name in command.tracks)
    ]
    if not streams or set(command.tracks) - {s.name for s in streams}:
        raise RecsError('Selected tracks must all belong to the chosen audio clock')
    if any(s.unmapped_fragments for s in streams):
        raise RecsError('Selected audio has unresolved timeline placement')
    extent = min(s.end for s in streams)
    if positions[1].frame < positions[0].frame:
        raise RecsError('End marker precedes start marker on the selected clock')
    if any(p.frame > extent for p in positions):
        raise RecsError('Marker lies outside a selected track extent')
    start = positions[0].frame - round(Fraction(str(command.lead)) * rate)
    end = positions[1].frame + round(Fraction(str(command.tail)) * rate)
    actual_start, actual_end = max(0, start), min(extent, end)
    if actual_end <= actual_start:
        raise RecsError(
            'Marker interval is empty; select an end marker or add lead/tail'
        )
    plan = ExtractionPlan(
        recording=path,
        clock=command.clock,
        sample_rate=rate,
        markers=selected,
        tracks=[s.name for s in streams],
        requested_start_frame=start,
        requested_end_frame=end,
        start_frame=actual_start,
        end_frame=actual_end,
    )
    return plan, _arrangement(plan, document, streams)


def main(argv: list[str]) -> int:
    command = tyro.cli(ExtractCli, args=argv, prog='recs session extract')
    plan, edit = plan_extraction(command)
    if command.json_output:
        print(plan.model_dump_json(indent=2))
    else:
        print(
            f'Clock {plan.clock}: [{plan.start_frame}, {plan.end_frame}) frames '
            f'at {plan.sample_rate} Hz'
        )
        print(f'Tracks: {", ".join(plan.tracks)}')
        if (plan.start_frame, plan.end_frame) != (
            plan.requested_start_frame,
            plan.requested_end_frame,
        ):
            print('Lead/tail trimmed to the common selected-track extent.')
        print('Known gaps render as silence; no cross-clock alignment is inferred.')
    if command.destination is not None:
        if command.destination.resolve().is_relative_to(plan.recording.parent):
            raise RecsError(
                'Extraction destination must be outside the original session'
            )
        execute_edit(
            edit,
            Path.cwd(),
            command.destination,
            provenance={'marker_extraction': plan.model_dump(mode='json')},
        )
    return 0


def _position(marker: Marker, clock: str) -> MarkerPosition:
    positions = [p for p in marker.positions if p.clock_id == clock]
    if len(positions) != 1:
        raise RecsError(
            f'Marker {marker.number} has no unique position on {clock}; '
            'explicit alignment is required'
        )
    return positions[0]


def _arrangement(
    plan: ExtractionPlan, document: RecordingScore, streams: list[AudioStream]
) -> arrangement.ArrangementScore:
    tracks: list[arrangement.TrackSpec] = []
    clips: list[arrangement.ClipSpec] = []
    outputs: list[interface.Output] = []
    for stream in streams:
        ports = [
            p
            for p in document.outputs
            if isinstance(p.binding, interface.StreamBinding)
            and p.binding.stream == stream.name
            and p.binding.channels is None
        ]
        if len(ports) != 1:
            raise RecsError(
                f'Track {stream.name} requires one full-channel recording output'
            )
        audio = AudioType(timebase='audio', channels=stream.stream.channels)
        tracks.append(arrangement.TrackSpec(name=stream.name, stream=audio))
        clips.append(
            arrangement.ClipSpec(
                name=stream.name,
                track=stream.name,
                source=interface.OutputSelection(
                    name='recording', output=ports[0].name
                ),
                source_start=plan.start_frame,
                source_end=plan.end_frame,
                timeline_start=0,
            )
        )
        outputs.append(
            interface.Output(
                name=stream.name,
                stream=audio,
                binding=interface.MixBinding(track=stream.name),
            )
        )
    return arrangement.ArrangementScore(
        name='marker-extract',
        title='Marker extraction',
        timebases=[Timebase(name='audio', rate=Rate(numerator=plan.sample_rate))],
        outputs=outputs,
        destinations=[
            FileDestination(
                output=o.name,
                path=Path(f'audio/{o.name}.wav'),
                format=Format.wav,
                subtype=Subtype.float,
            )
            for o in outputs
        ],
        body=arrangement.Arrangement(
            timebase='audio',
            parts=[
                interface.Part(
                    name='recording',
                    score=interface.ScoreVersion(
                        path=os.path.relpath(plan.recording, Path.cwd())
                    ),
                )
            ],
            tracks=tracks,
            clips=clips,
        ),
    )
