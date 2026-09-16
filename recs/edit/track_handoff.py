"""Render aligned float WAV tracks and retain their source-clock evidence."""

import uuid
from pathlib import Path
from typing import Annotated, Literal

import soundfile
import tyro
from pydantic import BaseModel, Field
from ufor.arrangement import ArrangementScore
from ufor.recording import AudioStream, Gap

from ..base.errors import RecsError
from ..recording.markers import Marker, read_markers
from ..recording.read import read_recording
from .session import execute_edit
from .track_edit import track_arrangement


class HandoffCli(BaseModel, frozen=True):
    """Preview aligned tracks from one sealed segment; --destination writes the bundle.

    Frame bounds are half-open on one capture clock. No resampling or alignment
    between independent clocks is inferred. Output is 32-bit float WAV plus JSON.
    """

    path: Annotated[Path, tyro.conf.Positional]
    clock: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(gt=0)
    tracks: list[str] = Field(default_factory=list)
    """Exact stream IDs; default: all audio streams on the selected clock."""
    destination: Path | None = None


class HandoffTrack(BaseModel, frozen=True):
    stream_id: str
    source_id: str
    source_name: str | None
    track_name: str | None
    channels: list[str]
    path: str
    gaps: list[Gap]


class HandoffPlan(BaseModel, frozen=True):
    version: Literal[1] = 1
    recording: Path
    clock: str
    sample_rate: int
    start_frame: int
    end_frame: int
    encoding: Literal['WAV/FLOAT'] = 'WAV/FLOAT'
    tracks: list[HandoffTrack]
    markers: list[Marker]


def plan_handoff(command: HandoffCli) -> tuple[HandoffPlan, ArrangementScore]:
    path = command.path / 'recording.toml' if command.path.is_dir() else command.path
    path = path.resolve()
    document = read_recording(path)
    if document.body.state != 'sealed':
        raise RecsError('Track handoff requires a sealed recording')
    if document.body.continued_at or document.body.continued_from:
        raise RecsError('Track handoff currently requires a single unlinked segment')
    clocks = [t for t in document.timebases if t.name == command.clock]
    if not clocks or clocks[0].rate.denominator != 1:
        raise RecsError('Select an integer-rate audio clock')
    rate = clocks[0].rate.numerator
    streams = sorted(
        (
            s
            for s in document.body.streams
            if isinstance(s, AudioStream)
            and s.stream.timebase == command.clock
            and (not command.tracks or s.name in command.tracks)
        ),
        key=lambda s: s.name,
    )
    if not streams or set(command.tracks) - {s.name for s in streams}:
        raise RecsError('Selected tracks must all belong to the chosen audio clock')
    if any(s.unmapped_fragments for s in streams):
        raise RecsError('Selected audio has unresolved timeline placement')
    if command.start_frame >= command.end_frame or any(
        command.end_frame > s.end for s in streams
    ):
        raise RecsError('Interval must be nonempty and within every selected track')
    tracks = [
        HandoffTrack(
            stream_id=s.name,
            source_id=s.source_id,
            source_name=s.source_name,
            track_name=s.track_name,
            channels=s.stream.channels,
            path=f'audio/{i:04d}.wav',
            gaps=[
                Gap(
                    start=max(g.start, command.start_frame),
                    end=min(g.end, command.end_frame),
                    reason=g.reason,
                )
                for g in s.gaps
                if g.start < command.end_frame and g.end > command.start_frame
            ],
        )
        for i, s in enumerate(streams, 1)
    ]
    markers = []
    for marker in read_markers(path, document):
        positions = [p for p in marker.positions if p.clock_id == command.clock]
        if any(p.sample_rate != rate for p in positions) or len(positions) > 1:
            raise RecsError(f'Marker {marker.number} has inconsistent clock evidence')
        if positions and command.start_frame <= positions[0].frame < command.end_frame:
            markers.append(marker.model_copy(update={'positions': positions}))
    plan = HandoffPlan(
        recording=path,
        clock=command.clock,
        sample_rate=rate,
        start_frame=command.start_frame,
        end_frame=command.end_frame,
        tracks=tracks,
        markers=markers,
    )
    edit = track_arrangement(
        path, document, streams, command.start_frame, command.end_frame, rate
    )
    edit = edit.model_copy(
        update={
            'name': 'track-handoff',
            'title': 'Aligned track handoff',
            'destinations': [
                d.model_copy(update={'path': Path(t.path)})
                for d, t in zip(edit.destinations, tracks, strict=True)
            ],
        }
    )
    return plan, edit


def render_handoff(
    plan: HandoffPlan, edit: ArrangementScore, destination: Path
) -> Path:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise RecsError(f'Handoff destination already exists: {destination}')
    if destination.resolve().is_relative_to(plan.recording.parent):
        raise RecsError('Handoff destination must be outside the original session')
    staging = destination.with_name(
        f'.{destination.name}.recs-handoff-{uuid.uuid4().hex}'
    )
    try:
        execute_edit(
            edit,
            Path.cwd(),
            staging,
            provenance={'track_handoff': plan.model_dump(mode='json')},
        )
        (staging / 'handoff.json').write_text(plan.model_dump_json(indent=2))
        if destination.exists() or destination.is_symlink():
            raise RecsError(
                f'Handoff destination appeared during rendering: {destination}'
            )
        staging.rename(destination)
    except (OSError, RecsError, soundfile.SoundFileError, KeyboardInterrupt) as error:
        raise RecsError(
            f'Handoff not published; any partial work remains at {staging}: {error}'
        ) from error
    return destination


def main(argv: list[str]) -> int:
    command = tyro.cli(HandoffCli, args=argv, prog='recs session handoff')
    plan, edit = plan_handoff(command)
    print(plan.model_dump_json(indent=2))
    if command.destination is not None:
        render_handoff(plan, edit, command.destination)
    return 0
