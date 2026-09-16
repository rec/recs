"""Inspect a recording setup without starting capture or writing a session."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import numpy as np
import soundfile
import tyro
from pydantic import BaseModel, Field

from recs.base import times
from recs.base.errors import RecsError
from recs.cfg import cli, run_cli, settings, setup_profiles
from recs.cfg.aliases import Aliases
from recs.cfg.path_pattern import PathPattern
from recs.cfg.track_names import track_name
from recs.recording import recording_paths

from .device_lifecycle import DeviceLifecycle


class ReadinessCommand(BaseModel, frozen=True):
    """Inspect setup readiness; unlike preflight, no running daemon is required.

    Put recording options after --. Missing devices warn; invalid settings fail.
    This command never opens input streams or performs the test-input recording.
    """

    profile: str | None = None
    json_output: bool = False
    recs_options: Annotated[list[str], tyro.conf.Positional] = Field(
        default_factory=list
    )


class ReadyTrack(BaseModel, frozen=True):
    name: str
    channels: list[int]


class ReadySource(BaseModel, frozen=True):
    name: str
    sample_rate: int
    tracks: list[ReadyTrack]
    settings: dict[str, object]


class ReadinessReport(BaseModel, frozen=True):
    profile: str | None = None
    settings: dict[str, object]
    sources: list[ReadySource] = Field(default_factory=list)
    output_root: Path | None = None
    free_bytes: int | None = None
    input_pcm_bytes_per_second: int = 0
    input_pcm_seconds: float | None = None
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(
        default_factory=lambda: [
            'Inspection only: streams were not opened; devices and free space '
            'can change.',
            'Duration is continuous input-PCM equivalent, not a compressed-file '
            'prediction. '
            'Compression, silence suppression, other media, disk policy, and overhead '
            'make actual duration unknown; no finite upper estimate is available.',
            'MIDI/OSC settings are shown but endpoint availability is not probed.',
            'Run recs test-input separately only when you intend to make a recording.',
        ]
    )


def inspect_setup(loaded: settings.LoadedSettings) -> ReadinessReport:
    cfg = loaded.cfg
    warnings: list[str] = []
    failures: list[str] = []
    sources: list[ReadySource] = []
    rate = 0
    try:
        devices = cfg.input_devices
        if cfg.device.devices.name:
            warnings.append(
                'Device inventory comes from --devices, not live discovery.'
            )
        available_aliases: list[str] = []
        resolver = Aliases([], devices)
        for definition in cfg.device.alias:
            name, _, target = definition.partition('=')
            try:
                resolver.to_track((target or name).strip())
            except KeyError as error:
                if error.args[1] != 'unknown':
                    failures.append(f'Alias {name.strip()}: {error.args[1]} device')
                else:
                    warnings.append(
                        f'Alias {name.strip()}: source currently absent; capture '
                        'cannot resolve this alias until its target is present'
                    )
            except RecsError as error:
                failures.append(str(error))
            else:
                available_aliases.append(definition)
        resolver = Aliases(available_aliases, devices)
        selections: dict[str, list[str]] = {}
        for kind in ('include', 'exclude'):
            selections[kind] = []
            for selector in getattr(cfg.selection, kind):
                try:
                    resolver.to_track(selector)
                except KeyError as error:
                    if error.args[1] == 'unknown':
                        warnings.append(f'{kind} {selector}: no current device match')
                        selections[kind].append(selector)
                    else:
                        failures.append(f'{kind} {selector}: ambiguous device match')
                except RecsError as error:
                    failures.append(str(error))
                else:
                    selections[kind].append(selector)
        # Preserve the original effective settings in the report. This view only
        # permits inspection of valid selections alongside independent failures.
        inspected = cfg.model_copy(
            update={
                'device': cfg.device.model_copy(update={'alias': available_aliases}),
                'selection': cfg.selection.model_copy(update=selections),
            }
        )
        if cfg.selection.include and not selections['include']:
            selected = []
        else:
            selected = DeviceLifecycle.initial_tracks(inspected, loaded.tracks)
        for source, tracks in selected:
            try:
                effective = cfg.with_device_profile(source.name)
                for encoding in effective.audio.formats:
                    if not soundfile.check_format(encoding, effective.audio.subtype):
                        raise RecsError(
                            f'{source.name}: incompatible format/subtype: '
                            f'{encoding}/{effective.audio.subtype}'
                        )
                saved = loaded.tracks.get(source.key, [])
                for layout in saved:
                    channels = layout.channels
                    if (
                        len(channels) not in (1, 2)
                        or channels[0] < 1
                        or channels[-1] > source.channels
                        or (len(channels) == 2 and channels[1] != channels[0] + 1)
                    ):
                        raise RecsError(
                            f'{source.name}: invalid saved channel layout {channels}'
                        )
                sources.append(
                    ReadySource(
                        name=source.name,
                        sample_rate=source.samplerate,
                        tracks=[
                            ReadyTrack(
                                name=track_name(loaded.track_names, t) or t.name,
                                channels=list(t.channels),
                            )
                            for t in tracks
                        ],
                        settings=effective.model_dump(mode='json'),
                    )
                )
                rate += (
                    source.samplerate
                    * sum(len(t.channels) for t in tracks)
                    * np.dtype(effective.audio.sdtype).itemsize
                    * len(effective.audio.formats)
                )
            except (RecsError, ValueError) as error:
                failures.append(str(error))
        for name in sorted(loaded.tracks.keys() - devices.keys()):
            warnings.append(f'Saved layout {name}: source currently absent')
        if not sources:
            warnings.append('No audio tracks currently available for recording.')
        # Validate the profile file even if no device is currently connected.
        for name in cfg.device_profiles:
            cfg.with_device_profile(name)
    except (RecsError, OSError, ValueError, subprocess.SubprocessError) as error:
        failures.append(str(error))

    output_root = None
    free_bytes = None
    try:
        PathPattern(cfg.directory.output_directory)
        resolved = recording_paths.with_default_output_directory(cfg, times.timestamp())
        output_root = recording_paths.formatted_output_directory(
            resolved.directory.output_directory, times.timestamp()
        ).absolute()
        parent = next(
            p
            for p in (output_root, *output_root.parents)
            if p.exists() or p.is_symlink()
        )
        if not parent.is_dir():
            failures.append(f'Output parent is not a directory: {parent}')
        elif not os.access(parent, os.W_OK | os.X_OK):
            failures.append(f'Output parent is not writable/searchable: {parent}')
        else:
            free_bytes = shutil.disk_usage(parent).free
            if free_bytes <= cfg.recording.minimum_free_space:
                failures.append(
                    'Free space is at or below the configured minimum reserve.'
                )
    except (RecsError, OSError, ValueError) as error:
        failures.append(f'Output: {error}')
    usable = (
        max(0, free_bytes - cfg.recording.minimum_free_space)
        if free_bytes is not None
        else None
    )
    return ReadinessReport(
        profile=loaded.profile,
        settings=cfg.model_dump(mode='json'),
        sources=sources,
        output_root=output_root,
        free_bytes=free_bytes,
        input_pcm_bytes_per_second=rate,
        input_pcm_seconds=usable / rate if usable is not None and rate else None,
        warnings=warnings,
        failures=failures,
    )


def main(argv: list[str]) -> int:
    command = tyro.cli(ReadinessCommand, args=argv, prog='recs readiness')
    try:
        if command.profile is not None:
            loaded = setup_profiles.configured(command.profile, command.recs_options)
        else:
            cfg = tyro.cli(
                cli.CliCfg, args=command.recs_options, prog='recs readiness --'
            )
            loaded = settings.load(cfg, run_cli.cli_overrides(command.recs_options))
        report = inspect_setup(loaded)
    except (RecsError, OSError, ValueError) as error:
        report = ReadinessReport(
            profile=command.profile, settings={}, failures=[str(error)]
        )
    if command.json_output:
        print(report.model_dump_json(indent=2))
    else:
        print('Readiness failed' if report.failures else 'Readiness inspection passed')
        print(f'Output root: {report.output_root}')
        print(f'Free bytes: {report.free_bytes}')
        print(f'Input-PCM equivalent seconds: {report.input_pcm_seconds}')
        for source in report.sources:
            print(f'{source.name}: {source.sample_rate} Hz')
            for track in source.tracks:
                print(f'  {track.name}: channels {track.channels}')
            print('  Effective source settings:')
            print(json.dumps(source.settings, indent=2))
        for label, messages in [
            ('WARN', report.warnings),
            ('FAIL', report.failures),
            ('NOTE', report.limitations),
        ]:
            for message in messages:
                print(f'{label}: {message}')
        print('Effective setup settings:')
        print(json.dumps(report.settings, indent=2))
    return int(bool(report.failures))
