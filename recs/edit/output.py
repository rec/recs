from pathlib import Path

import soundfile

from recs.base.errors import RecsError
from recs.base.types import Format
from recs.edit.graph import EditGraph
from recs.model.arrangement import ArrangementDocument
from recs.model.streams import FileDestination


def validate_outputs(
    edit: ArrangementDocument, graph: EditGraph, destination: Path
) -> None:
    if destination.exists():
        raise RecsError(f'Output session directory already exists: {destination}')
    targets = {d.port: d for d in edit.destinations}
    if len(targets) != len(edit.destinations) or set(targets) != {
        o.id for o in edit.body.outputs
    }:
        raise RecsError(
            'Final render requires exactly one destination for every output port'
        )
    paths: list[Path] = []
    for port in edit.body.outputs:
        output = targets[port.id]
        path = destination / output.path
        resolved = path.resolve()
        audio_directory = (destination / 'audio').resolve()
        if not resolved.is_relative_to(audio_directory):
            raise RecsError(
                f'Output {output.port}: path must remain inside audio/: {output.path}'
            )
        if output.path.suffix.lower() != f'.{output.format}':
            raise RecsError(
                f'Output {output.port}: path extension does not match {output.format}'
            )
        if resolved in paths:
            raise RecsError(f'Duplicate output path: {output.path}')
        paths.append(resolved)
        channels = graph.widths[port.source]
        if output.format == Format.flac and channels > 8:
            raise RecsError(f'Output {output.port}: FLAC supports at most 8 channels')
        if output.format == Format.mp3 and channels > 2:
            raise RecsError(f'Output {output.port}: MP3 supports at most 2 channels')
        if not soundfile.check_format(output.format, output.subtype):
            detail = output.format
            if output.subtype is not None:
                detail += f'/{output.subtype}'
            raise RecsError(f'Output {output.port}: unsupported format {detail}')


def open_output(
    output: FileDestination, path: Path, channels: int, sample_rate: int
) -> soundfile.SoundFile:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return soundfile.SoundFile(
            path,
            mode='w',
            samplerate=sample_rate,
            channels=channels,
            format=output.format,
            subtype=output.subtype,
        )
    except soundfile.LibsndfileError as e:
        raise RecsError(f'Cannot create output {path}: {e}') from e


def bit_depth(file: soundfile.SoundFile) -> int | None:
    subtype = str(file.subtype).upper()
    for bits in (8, 16, 20, 24, 32, 64):
        if str(bits) in subtype:
            return bits
    if subtype == 'FLOAT':
        return 32
    if subtype == 'DOUBLE':
        return 64
    return None
