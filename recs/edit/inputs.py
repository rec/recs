"""Host-side input selections used while authoring portable arrangements."""

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from ufor.base import Identifier, Model
from ufor.encoding import Format
from ufor.interface import Part
from ufor.recording import RecordingScore
from ufor.references import RecordSelector


class SourceSpec(Model):
    name: Identifier
    record: Path | None = None
    selector: RecordSelector | None = None
    file: Path | None = None
    memory: str | None = None
    channels: list[int] = Field(default_factory=list)
    input_format: Format | None = None

    @model_validator(mode='after')
    def selection(self) -> Self:
        if sum(v is not None for v in (self.record, self.file, self.memory)) != 1:
            raise ValueError('select exactly one recording, file, or prepared input')
        if self.record is not None:
            if self.selector is None:
                raise ValueError('recording input requires a selector')
        elif (
            not self.channels
            or self.channels != list(range(self.channels[0], self.channels[-1] + 1))
            or self.channels[0] < 0
        ):
            raise ValueError('file and prepared input channels must be consecutive')
        return self


def export_source(
    source: SourceSpec,
    definitions: dict[Path, RecordingScore] | None = None,
) -> tuple[Part, list[str]]:
    """Author a recording score for an explicit host input selection."""
    import os
    from hashlib import sha256

    from ufor.codec import score_toml
    from ufor.interface import Output, Part, ScoreVersion, StreamBinding
    from ufor.recording import AudioFragment, AudioStream, Recording, RecordingScore
    from ufor.streams import AudioType
    from ufor.time import Rate, Timebase

    from recs.edit.record import resolve_input
    from recs.recording.files import sealed_asset
    from recs.recording.read import read_recording

    if source.memory is not None:
        channels = [f'channel-{i}' for i in source.channels]
        name = source.memory.replace(':', '/')
        indices = '-'.join(str(i) for i in source.channels)
        return Part(
            name=source.name,
            score=ScoreVersion(path=f'prepared/{name}/channels-{indices}.toml'),
        ), channels
    resolve_input(source, Path('.'))
    origin = source.record or source.file
    assert origin is not None
    origin = origin.resolve()
    if source.record is not None:
        assert source.selector is not None
        document = read_recording(origin)
        selected = next(
            s
            for s in document.body.streams
            if isinstance(s, AudioStream)
            and (s.source_name or s.source_id) == source.selector.source
            and (s.track_name or s.name) == source.selector.track
        )
        if source.input_format is not None:
            assets = {a.name: a for a in document.assets}
            selected = selected.model_copy(
                update={
                    'fragments': [
                        f
                        for f in selected.fragments
                        if assets[f.asset].encoding == source.input_format
                    ]
                }
            )
        document = document.model_copy(
            update={'body': document.body.model_copy(update={'streams': [selected]})}
        )
        indices = None if source.selector.channel is None else [source.selector.channel]
        channels = (
            selected.stream.channels
            if indices is None
            else [selected.stream.channels[i] for i in indices]
        )
        port = Output(
            name='audio',
            stream=selected.stream.model_copy(update={'channels': channels}),
            binding=StreamBinding(stream=selected.name, channels=indices),
        )
        document = document.model_copy(update={'outputs': [port]})
    else:
        asset = sealed_asset(origin, origin.parent, 'audio', origin.suffix.lstrip('.'))
        import soundfile

        info = soundfile.info(origin)
        clock = Timebase(name='audio', rate=Rate(numerator=info.samplerate))
        stream = AudioStream(
            name='audio',
            source_id=origin.name,
            stream=AudioType(
                timebase='audio',
                channels=[f'channel-{i}' for i in range(info.channels)],
            ),
            end=info.frames,
            fragments=[AudioFragment(asset='audio', start=0, count=info.frames)],
        )
        channels = [stream.stream.channels[i] for i in source.channels]
        port = Output(
            name='audio',
            stream=AudioType(timebase='audio', channels=channels),
            binding=StreamBinding(stream='audio', channels=source.channels),
        )
        document = RecordingScore(
            name=origin.stem,
            title=origin.name,
            assets=[asset],
            timebases=[clock],
            outputs=[port],
            body=Recording(state='sealed', streams=[stream]),
        )
    document = RecordingScore.model_validate(document.model_dump())
    text = score_toml(document)
    suffix = sha256(text.encode()).hexdigest()[:16]
    path = origin.with_name(f'{origin.stem}-{suffix}.recording.toml')
    if definitions is not None:
        definitions[path] = document
    elif not path.exists() or path.read_text() != text:
        path.write_text(text)
    return Part(
        name=source.name, score=ScoreVersion(path=os.path.relpath(path, Path.cwd()))
    ), channels
