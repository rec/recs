from pathlib import Path

import soundfile

from recs.base.errors import RecsError
from recs.base.types import Format
from recs.edit.graph import EditGraph
from recs.edit.schema import EditSpec, OutputSpec


def validate_outputs(edit: EditSpec, graph: EditGraph, destination: Path) -> None:
    if destination.exists():
        raise RecsError(f'Output session directory already exists: {destination}')
    paths: list[Path] = []
    for output in edit.outputs:
        if output.path is None or output.format is None:
            raise RecsError(
                f'Output {output.id}: final output requires path and format'
            )
        path = destination / output.path
        resolved = path.resolve()
        audio_directory = (destination / 'audio').resolve()
        if not resolved.is_relative_to(audio_directory):
            raise RecsError(
                f'Output {output.id}: path must remain inside audio/: {output.path}'
            )
        if output.path.suffix.lower() != f'.{output.format}':
            raise RecsError(
                f'Output {output.id}: path extension does not match {output.format}'
            )
        if resolved in paths:
            raise RecsError(f'Duplicate output path: {output.path}')
        paths.append(resolved)
        channels = graph.widths[output.source]
        if output.format == Format.flac and channels > 8:
            raise RecsError(f'Output {output.id}: FLAC supports at most 8 channels')
        if output.format == Format.mp3 and channels > 2:
            raise RecsError(f'Output {output.id}: MP3 supports at most 2 channels')
        if not soundfile.check_format(output.format, output.subtype):
            detail = output.format
            if output.subtype is not None:
                detail += f'/{output.subtype}'
            raise RecsError(f'Output {output.id}: unsupported format {detail}')


def open_output(
    output: OutputSpec, path: Path, channels: int, sample_rate: int
) -> soundfile.SoundFile:
    if output.format is None:
        raise RecsError(f'Output {output.id}: final output requires format')
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
