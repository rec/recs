"""Verify sealed recording assets, audio frames, and event counts."""

import base64
import hashlib
import json
from pathlib import Path

import mido
import soundfile
from pydantic import Field, TypeAdapter
from reccy.protocol.jsonl import Decompress
from ufor.assets import Asset
from ufor.base import Model
from ufor.events import StoredEvent
from ufor.recording import AudioFragment, AudioStream, EventStream, RecordingDocument

from ..base.errors import RecsError


class Verification(Model):
    asset_count: int
    byte_count: int
    audio_frames: int
    event_count: int
    gap_frames: int
    unresolved_audio_files: int = 0
    notes: list[str] = Field(default_factory=list)


def sealed_asset(path: Path, root: Path, identity: str, encoding: str) -> Asset:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise RecsError(f'Asset escapes the session directory: {path}')
    with resolved.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return Asset(
        id=identity,
        path=resolved.relative_to(root.resolve()).as_posix(),
        encoding=encoding,
        byte_length=resolved.stat().st_size,
        sha256=digest,
    )


def verify_recording(document: RecordingDocument, root: Path) -> Verification:
    """Check hashes, decode every audio frame, and count embedded events."""
    assets = {a.id: a for a in document.assets}
    paths: dict[str, Path] = {}
    for asset in document.assets:
        path = root / asset.path
        actual = sealed_asset(path, root, asset.id, asset.encoding)
        if actual.sha256 != asset.sha256 or actual.byte_length != asset.byte_length:
            raise RecsError(f'Asset bytes disagree with the recording: {asset.path}')
        paths[asset.id] = path
    clocks = {t.id: t for t in document.timebases}
    audio_frames = event_count = gap_frames = 0
    unresolved_audio_files = 0
    decoded: dict[str, tuple[int, int, int]] = {}
    for stream in document.body.streams:
        if isinstance(stream, AudioStream):
            clock = clocks[stream.stream.timebase]
            for fragment in [*stream.fragments, *stream.unmapped_fragments]:
                if fragment.asset not in decoded:
                    with soundfile.SoundFile(paths[fragment.asset]) as source:
                        frames = sum(
                            len(b)
                            for b in source.blocks(
                                blocksize=48000, dtype='float32', always_2d=True
                            )
                        )
                        if frames != source.frames:
                            raise RecsError(
                                'Audio payload is truncated: '
                                f'{assets[fragment.asset].path}'
                            )
                        decoded[fragment.asset] = (
                            frames,
                            source.channels,
                            source.samplerate,
                        )
                frames, channels, rate = decoded[fragment.asset]
                if (
                    channels != len(stream.stream.channels)
                    or rate * clock.rate.denominator != clock.rate.numerator
                ):
                    raise RecsError(
                        f'Audio layout or rate disagrees with stream {stream.id}'
                    )
                asset_start = (
                    fragment.asset_start if isinstance(fragment, AudioFragment) else 0
                )
                if asset_start + fragment.count > frames:
                    raise RecsError(
                        f'Fragment exceeds decoded audio: {assets[fragment.asset].path}'
                    )
                if not isinstance(fragment, AudioFragment) and fragment.count != frames:
                    raise RecsError(
                        'Unmapped fragment must describe its entire audio file'
                    )
                audio_frames += fragment.count
            unresolved_audio_files += len(stream.unmapped_fragments)
            gap_frames += sum(g.end - g.start for g in stream.gaps)
            continue
        event_count += verify_events(stream, paths)
    return Verification(
        asset_count=len(assets),
        byte_count=sum(a.byte_length for a in document.assets),
        audio_frames=audio_frames,
        event_count=event_count,
        gap_frames=gap_frames,
        unresolved_audio_files=unresolved_audio_files,
    )


def verify_events(stream: EventStream, paths: dict[str, Path]) -> int:
    event_count = 0
    decompress = Decompress(key='kind')
    previous: tuple[int, int] | None = None
    ordinals: set[int] = set()
    event_adapter = TypeAdapter(StoredEvent)
    for fragment in stream.fragments:
        path = paths[fragment.asset]
        if fragment.timing == 'smf':
            count = sum(not m.is_meta for t in mido.MidiFile(path).tracks for m in t)
        elif fragment.timing == 'osc_jsonl':
            count = 0
            with path.open() as source:
                for line in source:
                    value = json.loads(line)
                    if not isinstance(value, dict) or not isinstance(
                        value.get('kind'), str
                    ):
                        raise RecsError(f'Invalid OSC record in {path}')
                    record = next(decompress([value]))
                    if record['kind'] == 'osc':
                        data = record.get('data_b64')
                        if not isinstance(data, str):
                            raise RecsError(f'OSC packet bytes missing in {path}')
                        base64.b64decode(data, validate=True)
                        count += 1
        else:
            count = 0
            with path.open() as source:
                for line in source:
                    event = event_adapter.validate_json(line)
                    if (
                        fragment.start is None
                        or fragment.end is None
                        or not fragment.start <= event.tick < fragment.end
                    ):
                        raise RecsError(f'Event lies outside fragment extent: {path}')
                    if (
                        stream.event_kind is not None
                        and event.kind != stream.event_kind
                    ):
                        raise RecsError(f'Event kind disagrees with stream: {path}')
                    position = event.tick, event.ordinal
                    if (
                        previous is not None and position < previous
                    ) or event.ordinal in ordinals:
                        raise RecsError(
                            'Native events are out of order or repeat '
                            f'an ordinal: {path}'
                        )
                    previous = position
                    ordinals.add(event.ordinal)
                    count += 1
        if count != fragment.event_count:
            raise RecsError(f'Event count disagrees with the recording: {path}')
        event_count += count
    return event_count
