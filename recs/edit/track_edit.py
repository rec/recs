"""Build shared source-clock track edits for extraction and handoff."""

import os
from pathlib import Path

from ufor import arrangement, interface
from ufor.encoding import Format, Subtype
from ufor.recording import AudioStream, RecordingScore
from ufor.streams import AudioType, FileDestination
from ufor.time import Rate, Timebase

from ..base.errors import RecsError


def track_arrangement(
    path: Path,
    document: RecordingScore,
    streams: list[AudioStream],
    start_frame: int,
    end_frame: int,
    sample_rate: int,
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
                source_start=start_frame,
                source_end=end_frame,
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
        timebases=[Timebase(name='audio', rate=Rate(numerator=sample_rate))],
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
                        path=os.path.relpath(path, Path.cwd())
                    ),
                )
            ],
            tracks=tracks,
            clips=clips,
        ),
    )
