"""Recover a verified subset without modifying the original capture evidence."""

import shutil
import tempfile
import time
from enum import StrEnum, auto
from pathlib import Path
from typing import Annotated

import soundfile
import tyro
from pydantic import BaseModel, Field
from ufor.assets import Asset
from ufor.codec import score_toml

from ..base.errors import RecsError
from . import session_record
from .files import asset_content, sealed_asset, verify_recording
from .finalize import prepare_recording, read_capture_entries


class Decision(StrEnum):
    included = auto()
    unplaced = auto()
    omitted = auto()
    discarded = auto()


class RecoveryFile(BaseModel, frozen=True):
    path: str
    stream_id: str
    decision: Decision
    reason: str
    asset: Asset | None = None
    decoded_frames: int | None = None
    recovered_path: str | None = None


class RecoveryPlan(BaseModel, frozen=True):
    journal: Path
    evidence: Asset
    original_had_footer: bool = False
    files: list[RecoveryFile] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)


class RecoverCli(BaseModel, frozen=True):
    """Preview recovery of a stopped version 4 capture; --destination creates a copy.

    Audio is fully decoded for verification. Unfinished readable audio is retained
    as unplaced assets, not aligned tracks. No original files are changed.
    """

    path: Annotated[Path, tyro.conf.Positional]
    destination: Path | None = None
    json_output: Annotated[bool, tyro.conf.arg(name='json')] = False


def inspect_recovery(location: Path) -> RecoveryPlan:
    journal = (
        location / 'session-record.jsonl' if location.is_dir() else location
    ).resolve()
    evidence = sealed_asset(
        journal, journal.parent, 'capture-evidence', 'recs-session-v4'
    )
    try:
        entries, notes = read_capture_entries(journal)
    except (RecsError, ValueError) as error:
        return RecoveryPlan(journal=journal, evidence=evidence, failures=[str(error)])
    files: list[RecoveryFile] = []
    records = [
        e
        for e in entries
        if isinstance(
            e, session_record.AudioFileRecord | session_record.EventFileRecord
        )
    ]
    for index, path in enumerate(sorted({e.path for e in records})):
        group = [e for e in records if e.path == path]
        started = [e for e in group if e.type == 'file_started']
        finished = [e for e in group if e.type == 'file_finished']
        discarded = [e for e in group if e.type == 'file_discarded']
        decision = Decision.omitted
        asset = None
        frames = None
        try:
            if (
                len(started) != 1
                or len(finished) > 1
                or len(discarded) > 1
                or (finished and discarded)
            ):
                raise RecsError('Ambiguous or missing file lifecycle evidence')
            if any(e.stream_id != started[0].stream_id for e in group):
                raise RecsError('File identity changes within capture evidence')
            if discarded:
                decision, reason = (
                    Decision.discarded,
                    'Capture intentionally discarded this file',
                )
            elif finished:
                candidate, _ = prepare_recording(
                    journal, [entries[0], *started, *finished]
                )
                verify_recording(candidate, journal.parent)
                asset = next(
                    a for a in candidate.assets if a.name != 'original-journal'
                )
                decision, reason = (
                    Decision.included,
                    'Verified completion evidence and media',
                )
            elif isinstance(started[0], session_record.AudioFileRecord):
                asset = sealed_asset(
                    journal.parent / path,
                    journal.parent,
                    f'unplaced-{index}',
                    started[0].format,
                )
                with soundfile.SoundFile(journal.parent / path) as audio:
                    if (
                        started[0].sample_rate is not None
                        and started[0].sample_rate != audio.samplerate
                    ) or (
                        started[0].channels is not None
                        and started[0].channels != audio.channels
                    ):
                        raise RecsError(
                            'Audio layout or rate disagrees with its start record'
                        )
                    frames = sum(
                        len(b) for b in audio.blocks(blocksize=48_000, always_2d=True)
                    )
                    if frames != audio.frames:
                        raise RecsError('Decoded audio is truncated')
                decision = Decision.unplaced
                reason = (
                    'Readable audio without completion evidence; '
                    'native placement is unknown'
                )
            else:
                raise RecsError(
                    'Incomplete event files are not recovered by this version'
                )
        except (
            OSError,
            ValueError,
            RecsError,
            EOFError,
            soundfile.SoundFileError,
        ) as error:
            reason = str(error)
            asset = None
        files.append(
            RecoveryFile(
                path=path,
                stream_id=group[0].stream_id,
                decision=decision,
                reason=reason,
                asset=asset,
                decoded_frames=frames,
                recovered_path=f'media/{index:04d}{Path(path).suffix}'
                if asset is not None
                else None,
            )
        )
    failures: list[str] = []
    selected = _selected_entries(entries, files)
    try:
        # Check cross-file stream/layout/clock consistency before writing anything.
        prepare_recording(journal, selected)
    except (OSError, ValueError, RecsError, soundfile.SoundFileError) as error:
        failures.append(str(error))
    if not any(f.asset is not None for f in files):
        failures.append('No verifiable media is available for recovery')
    return RecoveryPlan(
        journal=journal,
        evidence=evidence,
        original_had_footer=any(
            isinstance(e, session_record.SessionFooter) for e in entries
        ),
        files=files,
        failures=failures,
        notes=[
            *notes,
            'Sealed output means recovery completed, '
            'not that the original capture was complete.',
            'Unplaced audio remains an asset only, '
            'with no invented frame range or output port.',
            'Only journal-referenced files in this segment are inspected; '
            'continuations are not followed.',
        ],
    )


def recover(plan: RecoveryPlan, destination: Path) -> Path:
    if plan.failures:
        raise RecsError('; '.join(plan.failures))
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise RecsError(f'Recovery destination already exists: {destination}')
    if destination.resolve().is_relative_to(plan.journal.parent):
        raise RecsError('Recovery destination must be outside the original session')
    actual = sealed_asset(
        plan.journal, plan.journal.parent, plan.evidence.name, plan.evidence.encoding
    )
    if actual != plan.evidence:
        raise RecsError('Capture journal changed since inspection; inspect again')
    entries, _ = read_capture_entries(plan.journal)
    selected = _selected_entries(entries, plan.files)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f'.{destination.name}.recs-recovery-', dir=destination.parent
        )
    )
    try:
        (staging / 'evidence').mkdir()
        original = staging / 'evidence/session-record.jsonl'
        shutil.copy2(plan.journal, original)
        copied = sealed_asset(
            original, staging, plan.evidence.name, plan.evidence.encoding
        )
        if asset_content(copied).sha256 != asset_content(plan.evidence).sha256:
            raise RecsError('Capture journal changed while copying')
        paths: dict[str, str] = {}
        unplaced: list[Asset] = []
        for item in plan.files:
            if item.asset is None:
                continue
            relative = item.recovered_path
            assert relative is not None
            target = staging / relative
            target.parent.mkdir(exist_ok=True)
            source = (plan.journal.parent / item.path).resolve()
            if not source.is_relative_to(plan.journal.parent):
                raise RecsError(f'Media escapes the original session: {item.path}')
            shutil.copy2(source, target)
            asset = sealed_asset(target, staging, item.asset.name, item.asset.encoding)
            if asset.content != asset_content(item.asset):
                raise RecsError(f'Media changed since inspection: {item.path}')
            paths[item.path] = relative
            if item.decision == Decision.unplaced:
                unplaced.append(asset)
        report = staging / 'recovery-report.json'
        report.write_text(plan.model_dump_json(indent=2))
        started = time.time()
        now = session_record.timestamp_to_json(started)
        writer = session_record.SessionRecordWriter(
            staging / 'session-record.jsonl',
            started_at=now,
            application={'name': 'recs recovery'},
        )
        try:
            writer.write(
                session_record.EventRecord(
                    type='recovery_completed',
                    timestamp=now,
                    metadata={
                        'original_journal': 'evidence/session-record.jsonl',
                        'report': 'recovery-report.json',
                        'media_paths': paths,
                        'seal_means': 'recovery_completed',
                    },
                )
            )
            for entry in selected[1:]:
                if isinstance(
                    entry,
                    session_record.AudioFileRecord | session_record.EventFileRecord,
                ):
                    entry = entry.model_copy(update={'path': paths[entry.path]})
                writer.write(entry)
            writer.write(
                session_record.SessionFooter(
                    ended_at=session_record.timestamp_to_json(time.time()),
                    duration_seconds=max(0, time.time() - started),
                )
            )
        finally:
            writer.close()
        document, _ = prepare_recording(writer.path)
        document = document.model_copy(
            update={
                'assets': [
                    *document.assets,
                    copied,
                    *unplaced,
                    sealed_asset(report, staging, 'recovery-report', 'json'),
                ]
            }
        )
        verify_recording(document, staging)
        (staging / 'recording.toml').write_text(score_toml(document))
        if destination.exists() or destination.is_symlink():
            raise RecsError(
                f'Recovery destination appeared during recovery: {destination}'
            )
        staging.rename(destination)
    except (
        OSError,
        ValueError,
        RecsError,
        soundfile.SoundFileError,
        KeyboardInterrupt,
    ) as error:
        raise RecsError(
            f'Recovery not published; partial work retained at {staging}: {error}'
        ) from error
    return destination


def main(argv: list[str]) -> int:
    command = tyro.cli(RecoverCli, args=argv, prog='recs session recover')
    plan = inspect_recovery(command.path)
    if command.json_output:
        print(plan.model_dump_json(indent=2))
    else:
        for item in plan.files:
            print(f'{item.decision}: {item.path}: {item.reason}')
        for message in [*plan.notes, *plan.failures]:
            print(message)
    if command.destination is not None:
        recover(plan, command.destination)
    return int(bool(plan.failures))


def _selected_entries(
    entries: list[session_record.Record], files: list[RecoveryFile]
) -> list[session_record.Record]:
    included = {f.path for f in files if f.decision == Decision.included}
    sources = {f.stream_id for f in files if f.decision == Decision.included}
    selected: list[session_record.Record] = [entries[0]]
    for entry in entries[1:]:
        if isinstance(
            entry, session_record.AudioFileRecord | session_record.EventFileRecord
        ):
            if entry.path in included:
                selected.append(entry)
        elif isinstance(entry, session_record.AudioTimelineRecord):
            if entry.stream_id in sources:
                selected.append(entry)
        elif isinstance(entry, session_record.ClockRecord):
            selected.append(entry)
        elif isinstance(entry, session_record.EventRecord) and entry.type in {
            'mark',
            'key_pressed',
            'key_released',
        }:
            selected.append(entry)
    return selected
