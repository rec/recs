from pathlib import Path

import soundfile
from pydantic import BaseModel, ConfigDict

from recs.base.errors import RecsError
from recs.base.types import Format
from recs.model import recording
from recs.model.arrangement import ArrangementDocument, SourceSpec
from recs.model.assets import Asset
from recs.model.recording import AudioStream
from recs.recording.files import sealed_asset
from recs.recording.read import read_recording_chain


class AudioFragment(BaseModel, frozen=True):
    path: Path
    start: int
    end: int
    channels: int
    channel_offset: int = 0
    asset_start: int = 0

    model_config = ConfigDict(extra='forbid')


class ResolvedSource(BaseModel, frozen=True):
    id: str
    record: Path | None
    file: Path | None
    session_id: str | None
    selector: str
    channels: int
    sample_rate: int
    timeline_end: int
    fragments: list[AudioFragment]

    model_config = ConfigDict(extra='forbid')


def resolve_sources(
    edit: ArrangementDocument, edit_directory: Path
) -> dict[str, ResolvedSource]:
    resolved = {
        source.id: _resolve_source(source, edit_directory)
        for source in edit.body.sources
    }
    wrong_rates = [
        f'{s.id}: {s.sample_rate}'
        for s in resolved.values()
        if s.sample_rate != edit.timebases[0].rate.numerator
    ]
    if wrong_rates:
        raise RecsError(
            f'Edit sample rate is {edit.timebases[0].rate.numerator}, but sources have '
            + ', '.join(wrong_rates)
        )
    return resolved


def _resolve_source(source: SourceSpec, edit_directory: Path) -> ResolvedSource:
    if source.file is not None:
        return _resolve_file_source(source, edit_directory)
    if source.memory is not None:
        raise RecsError(
            f'Source {source.id}: memory source is valid only inside a composition'
        )
    assert source.record is not None
    assert source.selector is not None
    record_path = (edit_directory / source.record).resolve()
    if not record_path.is_file():
        raise RecsError(
            f'Source {source.id}: session record does not exist: {record_path}'
        )
    records = read_recording_chain(record_path)
    selected = [
        (p, d, s)
        for p, d in records
        for s in d.body.streams
        if isinstance(s, AudioStream)
        and (s.source_name or s.source_id) == source.selector.source
        and (s.track_name or s.id) == source.selector.track
    ]
    if not selected:
        raise RecsError(
            f'Source {source.id}: selector {source.selector!r} matches no audio stream'
        )
    if any(s.unmapped_fragments for _, _, s in selected):
        raise RecsError(
            f'Source {source.id}: timeline placement is unresolved; '
            'recorded samples cannot be placed automatically'
        )
    if any(d.body.state != 'sealed' for _, d, _ in selected):
        raise RecsError(f'Source {source.id}: recording is still open')
    widths = {len(s.stream.channels) for _, _, s in selected}
    clocks = [
        t for _, d, s in selected for t in d.timebases if t.id == s.stream.timebase
    ]
    if any(t.rate.denominator != 1 for t in clocks):
        raise RecsError(
            f'Source {source.id}: this renderer requires integer audio sample rates'
        )
    rates = {t.rate.numerator for t in clocks}
    if len(widths) != 1 or len(rates) != 1:
        raise RecsError(f'Source {source.id}: inconsistent audio metadata')
    file_width = next(iter(widths))
    rate = next(iter(rates))
    offset = source.selector.channel
    if offset is not None and offset >= file_width:
        raise RecsError(
            f'Source {source.id}: channel offset {offset} exceeds width {file_width}'
        )
    width = 1 if offset is not None else file_width
    variants: dict[
        tuple[int, int], list[tuple[Path, Asset, recording.AudioFragment]]
    ] = {}
    for path, document, stream in selected:
        assets = {a.id: a for a in document.assets}
        for fragment in stream.fragments:
            variants.setdefault(
                (fragment.start, fragment.start + fragment.count), []
            ).append((path.parent, assets[fragment.asset], fragment))
    fragments: list[AudioFragment] = []
    verified: set[Path] = set()
    for (start, end), choices in sorted(variants.items()):
        if source.input_format is not None:
            choices = [c for c in choices if c[1].encoding == source.input_format]
        else:
            for encoding in Format:
                if preferred := [c for c in choices if c[1].encoding == encoding]:
                    choices = preferred
                    break
        if len(choices) != 1:
            raise RecsError(
                f'Source {source.id}: ambiguous variants for frames {start}:{end}'
            )
        directory, asset, span = choices[0]
        path = directory / asset.path
        if path not in verified:
            actual = sealed_asset(path, directory, asset.id, asset.encoding)
            if actual.sha256 != asset.sha256 or actual.byte_length != asset.byte_length:
                raise RecsError(
                    f'Source {source.id}: asset bytes disagree with recording: '
                    f'{asset.path}'
                )
            verified.add(path)
        info = soundfile.info(path)
        if (
            info.channels != file_width
            or info.samplerate != rate
            or span.asset_start + span.count > info.frames
        ):
            raise RecsError(
                f'Source {source.id}: file metadata disagrees with recording: '
                f'{asset.path}'
            )
        fragments.append(
            AudioFragment(
                path=path,
                start=start,
                end=end,
                channels=width,
                channel_offset=offset or 0,
                asset_start=span.asset_start,
            )
        )
    if any(a.end > b.start for a, b in zip(fragments, fragments[1:])):
        raise RecsError(
            f'Source {source.id}: overlapping source ranges across recordings'
        )
    return ResolvedSource(
        id=source.id,
        record=record_path,
        file=None,
        session_id=records[0][1].id,
        selector=f'{source.selector.source}:{source.selector.track}',
        channels=width,
        sample_rate=rate,
        timeline_end=max(s.end for _, _, s in selected),
        fragments=fragments,
    )


def _resolve_file_source(source: SourceSpec, edit_directory: Path) -> ResolvedSource:
    assert source.file is not None
    path = (edit_directory / source.file).resolve()
    if not path.is_file():
        raise RecsError(f'Source {source.id}: audio file does not exist: {path}')
    try:
        info = soundfile.info(path)
    except soundfile.LibsndfileError as e:
        raise RecsError(f'Source {source.id}: cannot read {path}: {e}') from e
    first = source.channels[0]
    if source.channels[-1] >= info.channels:
        raise RecsError(
            f'Source {source.id}: channel {source.channels[-1]} exceeds '
            f'file width {info.channels}'
        )
    return ResolvedSource(
        id=source.id,
        record=None,
        file=path,
        session_id=None,
        selector=f'{path.name}:{source.channels[0]}-{source.channels[-1]}',
        channels=len(source.channels),
        sample_rate=info.samplerate,
        timeline_end=info.frames,
        fragments=[
            AudioFragment(
                path=path,
                start=0,
                end=info.frames,
                channels=len(source.channels),
                channel_offset=first,
            )
        ],
    )
