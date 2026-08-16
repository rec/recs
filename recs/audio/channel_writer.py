import contextlib
import time
from collections.abc import Iterable, Sequence
from datetime import datetime
from functools import partial
from pathlib import Path
from threading import Lock
from typing import Any

from numpy.typing import NDArray
from overrides import override
from soundfile import SoundFile
from threa import Runnable

from recs.base.state import ChannelState
from recs.base.types import SDTYPE, Active, Format, SdType
from recs.cfg import time_settings, track_names
from recs.cfg.cfg import Cfg
from recs.cfg.track import Track
from recs.cfg.track_names import DeviceTrackNames
from recs.misc import counter, file_list

from .block import Block, Blocks
from .file_opener import FileOpener
from .header_size import header_size

URL = 'https://github.com/rec/recs'

BUFFER = 0x80
MAX_WAV_SIZE = 0x1_0000_0000 - BUFFER

ITEMSIZE = {
    SdType.float32: 4,
    SdType.int16: 2,
    SdType.int32: 4,
}

BLOCK_FUZZ = 2


class ChannelWriter(Runnable):
    bytes_in_file: int = 0

    frames_in_file: int = 0
    frames_written: int = 0  # Used elsewhere

    largest_file_size: int = 0
    longest_file_frames: int = 0

    timestamp: float = 0
    timeline_frame: int = 0
    max_write_seconds: float = 0.0

    _sfs: Sequence[SoundFile] = ()

    @property
    def active(self) -> Active:
        return Active.active if self._sfs else Active.inactive

    def __init__(
        self, cfg: Cfg, times: time_settings.TimeSettings[int], track: Track
    ) -> None:
        super().__init__()

        self.cfg = cfg
        self.do_not_record = (
            cfg.general.dry_run or cfg.general.calibrate or cfg.general.silence_preview
        )
        self.metadata = cfg.metadata_dict
        self.times = times
        self.track = track
        self.noise_floor = _noise_floor(cfg, track)
        self.track_names: DeviceTrackNames = {}

        self._blocks = Blocks()
        self._lock = Lock()

        if track.source.format is None or 'formats' in cfg.model_fields_set:
            self.formats = cfg.audio.formats
        else:
            self.formats = [track.source.format]

        subtype = cfg.audio.subtype
        sdtype = cfg.audio.sdtype or SDTYPE

        self.files_written = file_list.FileList()
        self.file_end_frames: dict[Path, int] = {}
        self.file_end_timestamps: dict[Path, float] = {}
        self.file_start_frames: dict[Path, int] = {}
        self.file_start_timestamps: dict[Path, float] = {}
        self.frame_size = ITEMSIZE[sdtype] * len(track.channels)
        self.longest_file_frames = times.longest_file_time

        opener = partial(
            FileOpener,
            channels=len(track.channels),
            samplerate=track.source.samplerate,
            subtype=subtype,
        )

        self.openers = [opener(format=f) for f in self.formats]
        self._volume = counter.MovingBlock(times.moving_average_time)

        def size(f: str) -> int:
            return (
                MAX_WAV_SIZE
                if f == Format.wav and not self.cfg.recording.infinite_length
                else 0
            )

        self.largest_file_size = max(0, *(size(f) for f in self.formats))

    def set_track_names(self, names: DeviceTrackNames) -> None:
        self.track_names = names

    def set_cfg(self, cfg: Cfg, times: time_settings.TimeSettings[int]) -> None:
        self.cfg = cfg
        self.do_not_record = (
            cfg.general.dry_run or cfg.general.calibrate or cfg.general.silence_preview
        )
        self.metadata = cfg.metadata_dict
        self.times = times
        self.noise_floor = _noise_floor(cfg, self.track)
        self.longest_file_frames = times.longest_file_time

    def to_block(self, array: NDArray) -> Block:
        return Block(block=array[:, self.track.slice])

    def receive_update(
        self,
        block: Block,
        timestamp: float,
        should_record: bool | None = None,
        timeline_frame: int = 0,
    ) -> ChannelState:
        with self._lock:
            if should_record is None:
                should_record = self.should_record(block)
            return self._receive_block(block, timestamp, should_record, timeline_frame)

    def should_record(self, block: Block) -> bool:
        return (
            self.times.record_everything
            or block.volume >= time_settings.db_to_amplitude(self.noise_floor)
        )

    @override
    def stop(self) -> None:
        with self._lock:
            self.running = False
            self._write_and_close()
            self.stopped = True

    def _close(self) -> None:
        sfs, self._sfs = self._sfs, ()
        for sf in sfs:
            if sf.frames and sf.frames >= self.times.shortest_file_time:
                sf.close()
            else:
                with contextlib.suppress(OSError, RuntimeError):
                    sf.close()
                with contextlib.suppress(OSError):
                    Path(sf.name).unlink()

    def _open(self, offset: int) -> Sequence[SoundFile]:
        timestamp = self.timestamp + offset / self.track.source.samplerate
        date = datetime.fromtimestamp(timestamp).isoformat()
        index = 1 + len(self.files_written)
        metadata = {'date': date, 'software': URL, 'tracknumber': str(index)}
        metadata |= self.metadata

        self.bytes_in_file = max(header_size(metadata, f) for f in self.formats)
        self.frames_in_file = 0

        if name := track_names.track_name(self.track_names, self.track):
            path = self.cfg.output_path_pattern.make_track_name_path(
                name, self.track, self.cfg.aliases, timestamp, index
            )
        else:
            path = self.cfg.output_path_pattern.make_path(
                self.track, self.cfg.aliases, timestamp, index
            )
        sfs = [o.create(metadata, path) for o in self.openers]
        paths = [Path(sf.name) for sf in sfs]
        start_frame = self.timeline_frame + offset
        self.file_start_frames.update(dict.fromkeys(paths, start_frame))
        self.file_start_timestamps.update(dict.fromkeys(paths, timestamp))
        self.file_end_frames.update(dict.fromkeys(paths, start_frame))
        self.file_end_timestamps.update(dict.fromkeys(paths, timestamp))
        self.files_written.extend(paths)
        return sfs

    def _receive_block(
        self,
        block: Block,
        timestamp: float,
        should_record: bool,
        timeline_frame: int = 0,
    ) -> ChannelState:
        saved_state = self._state(
            max_amp=max(block.max) / block.scale,
            min_amp=min(block.min) / block.scale,
        )

        dt = self.timestamp - timestamp
        self.timestamp = timestamp
        if timeline_frame:
            self.timeline_frame = timeline_frame
        self._volume.accumulate(block)

        if not self.do_not_record and (self._sfs or not self.stopped):
            expected_dt = len(block) / self.track.source.samplerate

            if dt > expected_dt * BLOCK_FUZZ:  # We were asleep, or otherwise lost time
                self._write_and_close()

            self._blocks.append(block)

            if should_record:
                if not self._sfs:  # Record some quiet before the first block
                    length = self.times.quiet_before_start + len(self._blocks[-1])
                    self._blocks.clip(length, from_start=True)

                self._write_blocks(self._blocks.blocks)
                self._blocks.clear()

            if self.stopped or self._blocks.duration > self.times.stop_after_quiet:
                self._write_and_close()

        return self._state() - saved_state

    def _state(self, **kwargs: Any) -> ChannelState:
        return ChannelState(
            file_count=len(self.files_written),
            file_size=self.files_written.total_size,
            is_active=bool(self._sfs),
            max_write_seconds=self.max_write_seconds,
            recorded_time=self.frames_written / self.track.source.samplerate,
            timestamp=self.timestamp,
            volume=list(self._volume.mean()),
            **kwargs,
        )

    def _write_and_close(self) -> None:
        # Record some quiet after the last block
        self._blocks.clip(self.times.quiet_after_end, from_start=False)

        if self._sfs:
            if self._blocks.blocks:
                self._write_blocks(self._blocks.blocks)
            self._blocks.clear()

        self._close()

    def _write_blocks(self, blox: Iterable[Block]) -> None:
        blocks = list(blox)

        # The last block in the list ends at self.timestamp so
        # we keep track of the sample offset before that
        offset = -sum(len(b) for b in blocks)

        for b in blocks:
            # Check if this block will overrun the file size or length
            remains: list[int] = []

            if self.longest_file_frames:
                remains.append(self.longest_file_frames - self.frames_in_file)

            if self._sfs and self.largest_file_size:
                file_bytes = self.largest_file_size - self.bytes_in_file
                remains.append(file_bytes // self.frame_size)

            if remains and min(remains) <= len(b):
                self._close()

            self._sfs = self._sfs or self._open(offset)
            for sf in self._sfs:
                start = time.monotonic()
                sf.write(b.block)
                self.max_write_seconds = max(
                    self.max_write_seconds, time.monotonic() - start
                )
            offset += len(b)
            end_frame = self.timeline_frame + offset
            end_timestamp = self.timestamp + offset / self.track.source.samplerate
            self.file_end_frames.update(
                dict.fromkeys((Path(sf.name) for sf in self._sfs), end_frame)
            )
            self.file_end_timestamps.update(
                dict.fromkeys((Path(sf.name) for sf in self._sfs), end_timestamp)
            )

            self.frames_in_file += len(b)
            self.frames_written += len(b)
            self.bytes_in_file += len(b) * self.frame_size


def _noise_floor(cfg: Cfg, track: Track) -> float:
    floors = cfg.recording.channel_noise_floors.get(track.source.name, {})
    if (noise_floor := floors.get(track.name)) is not None:
        return noise_floor
    return cfg.recording.noise_floor
