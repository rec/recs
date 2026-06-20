import json
import os
import sys
import typing as t
from multiprocessing import connection
from pathlib import Path

from threa import HasThread, Runnable, Runnables

from recs.base import RecsError, times
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.cfg import Cfg, FileSource, InputDevice

from . import gui_process, live
from .device_poller import DevicePoller
from .full_state import FullState
from .session_manifest import ManifestFile, SessionManifest, timestamp_to_json
from .source_process import SourceProcess
from .source_recorder import POLL_TIMEOUT, SourceUpdate
from .source_tracks import source_tracks

FRAME_CLOCK_GRACE = 5.0
MIN_FRAME_CLOCK_RATIO = 0.5


class Recorder(Runnables):
    def __init__(self, cfg: Cfg, *, display: bool = True) -> None:
        super().__init__()

        if not (all_tracks := list(source_tracks(cfg))):
            raise RecsError('No channels selected')

        self.cfg = cfg
        if cfg.console.gui:
            display_type = gui_process.GuiProcess
        else:
            display_type = live.Live
        self.live = display_type(self.rows, cfg) if display else None
        self.state = FullState(all_tracks)
        self.sources = {
            source.name: SourceProcess(cfg, tracks)
            for source, tracks in all_tracks
        }
        self.frames = dict.fromkeys(self.sources, 0)
        self.source_frames_at_start = dict.fromkeys(self.sources, 0)
        self.source_start_times = dict.fromkeys(self.sources, self.state.start_time)
        self.files_written: set[Path] = set()
        self.manifest_files: dict[Path, ManifestFile] = {}
        self.warnings: list[str] = []
        self.failed: set[str] = set()
        self.lag_reported: set[str] = set()
        self.present: set[str] = set()
        self.hardware = {
            name: source
            for name, source in self.sources.items()
            if isinstance(source.source, InputDevice)
        }
        self.files = {
            name: source
            for name, source in self.sources.items()
            if isinstance(source.source, FileSource)
        }

        runnables = tuple(self.files.values())
        self.poller = None
        if self.hardware:
            self.poller = DevicePoller(cfg.console.sleep_time_device)
            self.poller.poll()
            runnables += (self.poller,)
        if self.live and self.live.enabled:
            ui_time = 1 / self.cfg.console.ui_refresh_rate
            live_thread = HasThread(
                self.live.update,
                looping=True,
                name='LiveUpdate',
                pre_delay=ui_time,
            )
            runnables += live_thread, self.live

        self.runnables = runnables

    def start(self) -> None:
        super().start()
        Runnable.start(self)

    def rows(self) -> t.Iterator[dict[str, t.Any]]:
        return self.state.rows()

    def run(self) -> None:
        with raise_keyboard_interrupt_on_signal():
            try:
                self._run()
            except KeyboardInterrupt:
                print('Interrupted', file=sys.stderr)
            finally:
                self._receive_pending_updates()
                self._write_manifest()
                if self.cfg.general.calibrate or self.cfg.general.verbose:
                    print(json.dumps(self.state.db_ranges(), indent=2))
        self._summary()

    def _summary(self) -> None:
        print(f'Recording time: {_summary_time(self.state.elapsed_time)}')
        files = sorted(path for path in self.files_written if path.exists())
        if files:
            print('Files written:')
            for path in files:
                print(f'  {path}')
        else:
            print('Files written: none')

    def _run(self) -> None:
        with self:
            try:
                while self.running:
                    if self._display_closed():
                        break
                    self._poll_devices()
                    self._reap_sources()
                    sources = [
                        source
                        for source in self.sources.values()
                        if source.is_alive
                    ]
                    self.state.set_online(
                        source.name for source in sources if source.running
                    )
                    if self._done(sources):
                        break

                    connections = [source.connection for source in sources]
                    if not connections:
                        times.sleep(POLL_TIMEOUT)
                        continue
                    for c in connection.wait(connections, timeout=POLL_TIMEOUT):
                        self._receive_connection(t.cast(connection.Connection, c))
            finally:
                for source in self.hardware.values():
                    source.stop()
                for source in self.hardware.values():
                    source.join()

    def _done(self, sources: t.Sequence[SourceProcess]) -> bool:
        if self.files and not self.hardware:
            return not sources
        return self._invocation_expired() and not any(
            source.running for source in sources
        )

    def _invocation_expired(self) -> bool:
        total = self.cfg.recording.total_run_time
        return bool(total and self.state.elapsed_time >= total)

    def _display_closed(self) -> bool:
        return bool(self.live and self.live.closed)

    def _poll_devices(self) -> None:
        if self.poller is None or (snapshot := self.poller.latest()) is None:
            return

        compatible: set[str] = set()
        for name, source in self.hardware.items():
            info = snapshot.get(name)
            if info is None:
                self.failed.discard(name)
                source.stop()
                continue

            channels = int(info['max_input_channels'])
            if channels < source.required_channels:
                source.stop()
                if name not in self.failed:
                    warning = (
                        f'{name} has {channels} input channels; '
                        f'{source.required_channels} required'
                    )
                    print(f'ERROR: {warning}', file=sys.stderr)
                    self.warnings.append(warning)
                    self.failed.add(name)
                continue

            compatible.add(name)
            if name not in self.present:
                self.failed.discard(name)
            if (
                not source.started
                and name not in self.failed
                and not self._invocation_expired()
            ):
                source.start()
                self.source_frames_at_start[name] = self.frames[name]
                self.source_start_times[name] = times.timestamp()

        self.present = compatible

    def _reap_sources(self) -> None:
        for name, source in self.sources.items():
            if not source.started or source.is_alive:
                continue
            self._drain(source.connection)
            expected = not source.running
            source.join(timeout=0)
            for update in source.take_updates():
                self._receive_update(update)
            if name not in self.hardware:
                continue

            if not expected and name in self.present:
                self.failed.add(name)

    def _receive_pending_updates(self) -> None:
        for source in self.sources.values():
            for update in source.take_updates():
                self._receive_update(update)

    def _drain(self, conn: connection.Connection) -> None:
        while conn.poll():
            if not self._receive_connection(conn):
                break

    def _receive_connection(self, conn: connection.Connection) -> bool:
        try:
            msg = conn.recv()
        except EOFError:
            return False
        self._receive_update(t.cast(SourceUpdate, msg))
        return True

    def _receive_update(self, update: SourceUpdate) -> None:
        self.frames[update.source_name] += update.frames
        self.files_written.update(update.files)
        for file_record in update.file_records or []:
            self.manifest_files[file_record.path] = ManifestFile(
                path=str(file_record.path),
                source=self._manifest_source(file_record.source_name),
                track=file_record.track,
                channels=file_record.channels,
                sample_rate=file_record.sample_rate,
                bit_depth=file_record.bit_depth,
            )
        source = self.sources[update.source_name]
        self.state.update({update.source_name: update.channels})
        if source.running and not self._source_frame_clock_valid(source):
            source.stop()
            self.failed.add(update.source_name)
            return
        if source.running and self._source_time_expired(source):
            source.stop()

    def _source_frame_clock_valid(self, source: SourceProcess) -> bool:
        if source.name not in self.hardware:
            return True

        elapsed = times.timestamp() - self.source_start_times[source.name]
        if elapsed < FRAME_CLOCK_GRACE:
            return True

        frames = self.frames[source.name] - self.source_frames_at_start[source.name]
        recorded = frames / source.source.samplerate
        if recorded >= elapsed * MIN_FRAME_CLOCK_RATIO:
            return True

        if source.name not in self.lag_reported:
            warning = f'Device {source.name} lagging behind real time'
            print(warning, file=sys.stderr)
            self.warnings.append(warning)
            self.lag_reported.add(source.name)
        return False

    def _source_time_expired(self, source: SourceProcess) -> bool:
        total = self.cfg.recording.total_run_time
        if not total:
            return False

        target = round(total * source.source.samplerate)
        return self.frames[source.name] >= target

    def _write_manifest(self) -> None:
        files = [
            file
            for path, file in sorted(self.manifest_files.items())
            if path.exists()
        ]
        manifest = SessionManifest(
            started_at=timestamp_to_json(self.state.start_time),
            ended_at=timestamp_to_json(times.timestamp()),
            duration=self.state.elapsed_time,
            files=files,
            warnings=self.warnings,
        )
        manifest.write(self._manifest_path())

    def _manifest_source(self, source_name: str) -> str | None:
        if isinstance(self.sources[source_name].source, FileSource):
            return source_name
        return None

    def _manifest_path(self) -> Path:
        paths = sorted(path for path in self.files_written if path.exists())
        if paths:
            parent = Path(os.path.commonpath([path.parent for path in paths]))
            return parent / 'recs-session.json'

        output_directory = self.cfg.directory.output_directory
        if output_directory and '{' not in output_directory:
            return Path(output_directory) / 'recs-session.json'
        return Path('recs-session.json')


def _summary_time(seconds: float) -> str:
    value = times.to_str(seconds)
    if seconds < 60:
        return f'0:{value:0>6}'
    return value

