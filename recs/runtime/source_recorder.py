import contextlib
import uuid
from collections.abc import Sequence
from multiprocessing.connection import Connection
from pathlib import Path
from queue import Empty
from time import sleep
from typing import Any, cast

import numpy as np
from threa import Runnables
from ufor.encoding import Format

from recs.audio.channel_writer import ChannelWriter
from recs.audio.live_waveform import LiveWaveform
from recs.base.signals import raise_keyboard_interrupt_on_signal
from recs.base.state import ChannelState
from recs.base.types import SDTYPE, Active, SdType
from recs.base.waveform import (
    WaveformBatchData,
    WaveformLayoutData,
    WaveformTrackLayout,
)
from recs.cfg.cfg import Cfg
from recs.cfg.source import Update
from recs.cfg.track import Track
from recs.cfg.track_names import SourceTrackNames, track_name
from recs.recording.capture_events import SourceFileEvents, capture_clock_id
from recs.recording.session_record import MarkerPosition, timestamp_to_json
from recs.runtime.input_buffer import BufferedUpdate, InputBuffer
from recs.runtime.source_calibration import SourceCalibration
from recs.runtime.source_messages import SourceUpdate
from recs.runtime.source_transport import SourceControlHandler, SourceUpdateTransport

POLL_TIMEOUT = 0.05


class SourceControlApplier:
    def __init__(self, recorder: 'SourceRecorder', connection: Connection) -> None:
        self.recorder = recorder
        self.handler = SourceControlHandler(
            connection,
            self.set_cfg,
            self.set_session_directory,
            self.set_track_names,
            recorder.calibration.start,
            self.set_tracks,
            recorder.set_waveforms_enabled,
            self.set_writing_enabled,
        )

    def receive(self) -> None:
        self.handler.receive()

    def set_track_names(self, track_names: SourceTrackNames) -> None:
        self.recorder.track_names = track_names
        for writer in self.recorder.channel_writers:
            writer.set_track_names(track_names)
        self.recorder.reset_waveform()

    def set_session_directory(self, session_directory: Path) -> None:
        recorder = self.recorder
        recorder.session_directory = session_directory
        for writer in recorder.channel_writers:
            writer.set_session_directory(session_directory)

    def set_cfg(self, cfg: Cfg, revision: int | None = None) -> None:
        recorder = self.recorder
        recorder.cfg = cfg
        recorder.buffer.cfg = cfg
        recorder.times = cfg.times.scale(recorder.source.samplerate)
        for writer in recorder.channel_writers:
            writer.set_cfg(cfg, recorder.times)
        if revision is not None:
            recorder.pending_config_revisions.append(revision)

    def set_tracks(self, tracks: list[Track], track_names: SourceTrackNames) -> None:
        recorder = self.recorder
        for writer in recorder.channel_writers:
            if writer.active == Active.active:
                recorder.pending_active_channels.update(writer.track.channels)
            writer.stop()
        recorder.file_events.remember_finished_files(recorder.channel_writers)
        recorder.channel_writers = tuple(
            ChannelWriter(
                cfg=recorder.cfg,
                times=recorder.times,
                track=track,
                session_directory=recorder.session_directory,
            )
            for track in tracks
        )
        self.set_track_names(track_names)
        recorder.file_events.reset_writers(recorder.channel_writers)
        recorder.runnables = recorder.input_stream, *recorder.channel_writers
        recorder.pending_track_layout = [track.name for track in tracks]

    def set_writing_enabled(self, enabled: bool) -> None:
        recorder = self.recorder
        if enabled == recorder.writing_enabled:
            return
        if not enabled:
            for writer in recorder.channel_writers:
                try:
                    writer.stop()
                except OSError:
                    writer.stop_after_write_error()
            recorder.file_events.remember_finished_files(recorder.channel_writers)
            files, file_records = recorder.file_events.new_files(
                recorder.channel_writers, recorder.sample_bit_depth
            )
            recorder.writing_enabled = False
            recorder.update_transport.publish(
                SourceUpdate(
                    channels={},
                    files=files,
                    file_end_frames=recorder.file_events.end_frames(
                        recorder.channel_writers
                    ),
                    file_end_timestamps=recorder.file_events.end_timestamps(
                        recorder.channel_writers
                    ),
                    file_records=file_records,
                    file_spans=recorder.file_events.spans(recorder.channel_writers),
                    timelines=recorder.file_events.timelines(),
                    finished_files=recorder.file_events.finished(
                        recorder.channel_writers
                    ),
                    discarded_files=recorder.file_events.discarded(
                        recorder.channel_writers
                    ),
                    frames=0,
                    source_name=recorder.source.key,
                    writing_enabled=False,
                )
            )
            return
        tracks = [writer.track for writer in recorder.channel_writers]
        recorder.channel_writers = tuple(
            ChannelWriter(
                cfg=recorder.cfg,
                times=recorder.times,
                track=track,
                session_directory=recorder.session_directory,
            )
            for track in tracks
        )
        for writer in recorder.channel_writers:
            writer.set_track_names(recorder.track_names)
        recorder.file_events.reset_writers(recorder.channel_writers)
        recorder.runnables = recorder.input_stream, *recorder.channel_writers
        recorder.writing_enabled = True

    def suspend_after_write_error(self, error: OSError) -> None:
        recorder = self.recorder
        for writer in recorder.channel_writers:
            writer.stop_after_write_error()
        recorder.file_events.remember_finished_files(recorder.channel_writers)
        recorder.writing_enabled = False
        recorder.update_transport.publish(
            SourceUpdate(
                channels={},
                files=[],
                frames=0,
                source_name=recorder.source.key,
                writing_enabled=False,
                write_error=str(error),
            )
        )


class SourceRecorder(Runnables):
    sample_count: int = 0

    def __init__(
        self,
        cfg: Cfg,
        control_connection: Connection,
        session_directory: Path,
        stop_event: Any,
        tracks: Sequence[Track],
        update_transport: SourceUpdateTransport,
        track_names: SourceTrackNames | None = None,
        waveforms_enabled: bool = False,
        waveform_generation: int = 0,
        writing_enabled: bool = True,
    ) -> None:
        self.cfg = cfg
        self.session_directory = session_directory
        self.stop_event = stop_event
        self.update_transport = update_transport

        self.source = tracks[0].source
        assert all(t.source == self.source for t in tracks)

        self.name = self.cfg.aliases.display_name(self.source)
        self.buffer = InputBuffer(self.cfg, self.source.samplerate)
        self.times = self.cfg.times.scale(self.source.samplerate)
        self.channel_writers = tuple(
            ChannelWriter(
                cfg=self.cfg,
                times=self.times,
                track=t,
                session_directory=self.session_directory,
            )
            for t in tracks
        )
        self.file_events = SourceFileEvents(self.channel_writers, uuid.uuid4().hex)
        self.pending_active_channels: set[int] = set()
        self.pending_config_revisions: list[int] = []
        self.pending_track_layout: list[str] | None = None
        self.track_names: SourceTrackNames = {}
        self.waveform_generation = max(0, waveform_generation - int(waveforms_enabled))
        self.waveforms_enabled = False
        self.writing_enabled = writing_enabled
        self.waveform: LiveWaveform | None = None
        self.pending_waveform_layout: WaveformLayoutData | None = None
        self.calibration = SourceCalibration(self.source.samplerate)
        self.control = SourceControlApplier(self, control_connection)
        self.control.set_track_names(track_names or {})
        self.set_waveforms_enabled(waveforms_enabled)

        self.input_stream = self.source.input_stream(
            sdtype=cast(SdType, self.cfg.audio.sdtype),
            update_callback=self.buffer.put,
        )
        super().__init__(self.input_stream, *self.channel_writers)
        self.sample_bit_depth = (
            np.dtype((self.cfg.audio.sdtype or SDTYPE).value).itemsize * 8
        )

    def run(self) -> None:
        with (
            raise_keyboard_interrupt_on_signal(),
            contextlib.suppress(KeyboardInterrupt),
            self,
        ):
            pending: BufferedUpdate | None = None
            while self.running and not self.stop_event.is_set():
                self.control.receive()
                if not self.writing_enabled:
                    sleep(POLL_TIMEOUT)
                    continue
                try:
                    update = pending or self.buffer.get(timeout=POLL_TIMEOUT)
                    pending = None
                except Empty:
                    if not self.input_stream.running:
                        break
                else:
                    self.control.receive()
                    if self.writing_enabled:
                        self._receive_update(update)
                    else:
                        pending = update

        with contextlib.suppress(Empty):
            while True:
                update = self.buffer.get(block=False)
                self.control.receive()
                self._receive_update(update)
        self.file_events.remember_finished_files(self.channel_writers)
        files, records = self.file_events.new_files(
            self.channel_writers, self.sample_bit_depth
        )
        self.update_transport.publish(
            SourceUpdate(
                channels={},
                files=files,
                frames=0,
                source_name=self.source.key,
                file_records=records,
                file_end_frames=self.file_events.end_frames(self.channel_writers),
                file_end_timestamps=self.file_events.end_timestamps(
                    self.channel_writers
                ),
                file_spans=self.file_events.spans(self.channel_writers),
                timelines=self.file_events.timelines(),
                finished_files=self.file_events.finished(self.channel_writers),
                discarded_files=self.file_events.discarded(self.channel_writers),
                frame_count=self.buffer.timeline_frames,
            )
        )

    def set_waveforms_enabled(self, enabled: bool) -> None:
        if enabled == self.waveforms_enabled:
            return
        self.waveforms_enabled = enabled
        if not enabled:
            self.waveform = None
            self.pending_waveform_layout = None
            return
        self.reset_waveform()

    def reset_waveform(self) -> None:
        if not self.waveforms_enabled:
            return
        self.waveform_generation += 1
        tracks = [
            WaveformTrackLayout(
                channels=list(writer.track.channels),
                name=track_name(self.track_names, writer.track) or writer.track.name,
            )
            for writer in self.channel_writers
        ]
        self.waveform = LiveWaveform(
            source=self.source.key,
            sample_rate=self.source.samplerate,
            tracks=tracks,
            generation=self.waveform_generation,
            bucket_milliseconds=self.cfg.console.waveform_bucket_milliseconds,
            batch_milliseconds=self.cfg.console.waveform_batch_milliseconds,
        )
        self.pending_waveform_layout = self.waveform.layout

    def _receive_update(self, u: BufferedUpdate) -> None:
        update = u.update
        if Format.mp3 in self.cfg.audio.formats and update.array.dtype == np.float32:
            # mp3 and float32 crashes every time on my machine
            update = Update(update.array.astype(np.float64), update.timestamp)
            u = BufferedUpdate(update, u.start_frame, u.end_frame)

        end_timestamp = update.timestamp + len(update.array) / self.source.samplerate
        cb = {c: c.to_block(update.array) for c in self.channel_writers}
        waveform_batches: list[WaveformBatchData] = []
        waveform_warning: str | None = None
        if self.waveform is not None:
            try:
                waveform_batches = self.waveform.receive(
                    list(cb.values()), u.start_frame, update.timestamp
                )
            except ValueError as e:
                self.waveforms_enabled = False
                self.waveform = None
                self.pending_waveform_layout = None
                waveform_warning = (
                    f'Device {self.source.name}: Live waveforms disabled: {e}'
                )
        should_record = {c: c.should_record(b) for c, b in cb.items()}
        band_should_record = self.cfg.recording.band_mode and any(
            should_record.values()
        )
        msgs: dict[str, ChannelState] = {}
        try:
            for writer, block in cb.items():
                forced = bool(set(writer.track.channels) & self.pending_active_channels)
                msgs[writer.track.name] = writer.receive_update(
                    block,
                    end_timestamp,
                    should_record[writer] or band_should_record or forced,
                    u.end_frame,
                )
        except OSError as error:
            self.control.suspend_after_write_error(error)
            return
        self.pending_active_channels = set()
        calibration = self.calibration.update(cb)
        files, file_records = self.file_events.new_files(
            self.channel_writers, update.array.dtype.itemsize * 8
        )
        stats = self.buffer.stats.model_copy()
        stats.max_write_seconds = max(
            stats.max_write_seconds,
            *(state.max_write_seconds for state in msgs.values()),
        )
        buffer_warnings = self.buffer.warnings(self.source.name, update.timestamp)
        if waveform_warning is not None:
            buffer_warnings.append(waveform_warning)
        if update.status:
            if update.status == 'input overflow':
                buffer_warnings.append(
                    f'Device {self.source.name}: Dropped frame in PortAudio'
                )
            else:
                buffer_warnings.append(
                    f'Device {self.source.name} input status: {update.status}'
                )
        track_layout, self.pending_track_layout = self.pending_track_layout, None
        config_revisions, self.pending_config_revisions = (
            self.pending_config_revisions,
            [],
        )
        file_end_frames = self.file_events.end_frames(self.channel_writers)
        file_end_timestamps = self.file_events.end_timestamps(self.channel_writers)
        waveform_layout, self.pending_waveform_layout = (
            self.pending_waveform_layout,
            None,
        )
        self.update_transport.publish(
            SourceUpdate(
                channels=msgs,
                files=files,
                frames=len(update.array),
                source_name=self.source.key,
                timestamp=end_timestamp,
                buffer_stats=stats,
                buffer_warnings=buffer_warnings,
                file_records=file_records,
                file_end_frames=file_end_frames,
                file_spans=self.file_events.spans(self.channel_writers),
                timelines=self.file_events.timelines(),
                finished_files=self.file_events.finished(self.channel_writers),
                discarded_files=self.file_events.discarded(self.channel_writers),
                file_end_timestamps=file_end_timestamps,
                frame_count=u.end_frame,
                marker_position=MarkerPosition(
                    source=self.source.key,
                    clock_id=capture_clock_id(
                        self.file_events.capture_id or self.source.name
                    ),
                    frame=u.end_frame,
                    sample_rate=self.source.samplerate,
                    observed_at=timestamp_to_json(end_timestamp),
                ),
                track_state_frames=dict.fromkeys(msgs, u.end_frame),
                track_state_timestamps=dict.fromkeys(msgs, end_timestamp),
                calibration=calibration,
                track_layout=track_layout,
                config_revisions_applied=config_revisions or None,
                waveform_layout=waveform_layout,
                waveform_batches=waveform_batches or None,
            )
        )

        self.sample_count += len(update.array)
        if (total := self.times.total_run_time) and self.sample_count >= total:
            self.running = False
