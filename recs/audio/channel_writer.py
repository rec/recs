import contextlib
import typing as t
from datetime import datetime
from pathlib import Path
from threading import Lock

from overrides import override
from soundfile import SoundFile
from threa import Runnable

from recs.base.state import ChannelState
from recs.base.types import SDTYPE, Active, Format, SdType
from recs.cfg import Cfg, Track, device, time_settings
from recs.misc import counter, file_list

from .block import Block, Blocks
from .file_opener import FileOpener
from .header_size import header_size

URL = 'https://github.com/rec/recs'

BUFFER = 128
FORMAT_TO_SIZE_LIMIT = {
    Format.aiff: 0x8000_0000,
    Format.wav: 0x1_0000_0000,
}

ITEMSIZE = {
    SdType.float32: 4,
    SdType.int16: 2,
    SdType.int32: 4,
}

BLOCK_FUZZ = 2


class ChannelWriter(Runnable):
    bytes_in_this_file: int = 0

    frames_in_this_file: int = 0
    frames_written: int = 0  # Used elsewhere

    largest_file_size: int = 0
    longest_file_frames: int = 0

    timestamp: float = 0

    _sf: SoundFile | None = None

    @property
    def active(self) -> Active:
        return Active.active if self._sf else Active.inactive

    def __init__(
        self, cfg: Cfg, times: time_settings.TimeSettings[int], track: Track
    ) -> None:
        super().__init__()

        self.do_not_record = cfg.dry_run or cfg.calibrate
        self.format = cfg.format
        self.metadata = cfg.metadata
        self.times = times
        self.track = track

        self._blocks = Blocks()
        self._lock = Lock()

        self.files_written = file_list.FileList()
        self.frame_size = ITEMSIZE[cfg.sdtype or SDTYPE] * len(track.channels)
        self.longest_file_frames = times.longest_file_time
        self.opener = FileOpener(cfg, track)
        self._volume = counter.MovingBlock(times.moving_average_time)

        if not cfg.infinite_length:
            largest = FORMAT_TO_SIZE_LIMIT.get(cfg.format, 0)
            self.largest_file_size = max(largest - BUFFER, 0)

    def update(self, update: device.Update) -> ChannelState:
        block = Block(update.array[:, self.track.slice])
        with self._lock:
            return self._receive_block(block, update.timestamp)

    @override
    def stop(self) -> None:
        with self._lock:
            self.running = False
            self._write_and_close()
            self.stopped = True

    def _close(self) -> None:
        sf, self._sf = self._sf, None
        if sf and sf.frames and sf.frames >= self.times.shortest_file_time:
            sf.close()
        elif sf:
            with contextlib.suppress(Exception):
                sf.close()
            with contextlib.suppress(Exception):
                Path(sf.name).unlink()

    def _open(self, offset: int) -> SoundFile:
        timestamp = self.timestamp - offset / self.track.device.samplerate
        ts = datetime.fromtimestamp(timestamp)

        index = 1 + len(self.files_written)

        metadata = {'date': ts.isoformat(), 'software': URL, 'tracknumber': str(index)}
        metadata |= self.metadata

        self.bytes_in_this_file = header_size(metadata, self.format)
        self.frames_in_this_file = 0

        sf = self.opener.create(metadata, timestamp, index)
        self.files_written.append(Path(sf.name))
        return sf

    def _receive_block(self, block: Block, timestamp: float) -> ChannelState:
        saved_state = self._state(
            max_amp=max(block.max) / block.scale,
            min_amp=min(block.min) / block.scale,
        )

        dt = self.timestamp - timestamp
        self.timestamp = timestamp
        self._volume(block)

        if not self.do_not_record and (self._sf or not self.stopped):
            expected_dt = len(block) / self.track.device.samplerate

            if dt > expected_dt * BLOCK_FUZZ:  # We were asleep, or otherwise lost time
                self._write_and_close()

            self._blocks.append(block)

            if block.volume >= self.times.noise_floor_amplitude:
                if not self._sf:  # Record some quiet before the first block
                    length = self.times.quiet_before_start + len(self._blocks[-1])
                    self._blocks.clip(length, from_start=True)

                self._write_blocks(self._blocks)
                self._blocks.clear()

            if self.stopped or self._blocks.duration > self.times.stop_after_quiet:
                self._write_and_close()

        return self._state() - saved_state

    def _state(self, **kwargs) -> ChannelState:
        return ChannelState(
            file_count=len(self.files_written),
            file_size=self.files_written.total_size,
            is_active=bool(self._sf),
            recorded_time=self.frames_written / self.track.device.samplerate,
            timestamp=self.timestamp,
            volume=tuple(self._volume.mean()),
            **kwargs,
        )

    def _write_and_close(self) -> None:
        # Record some quiet after the last block
        removed = self._blocks.clip(self.times.quiet_after_end, from_start=False)

        if self._sf and removed:
            self._write_blocks(reversed(removed))

        self._close()

    def _write_blocks(self, blox: t.Iterable[Block]) -> None:
        blocks = list(blox)

        # The last block in the list ends at self.timestamp so
        # we keep track of the sample offset before that
        offset = -sum(len(b) for b in blocks)

        for b in blocks:
            # Check if this block will overrun the file size or length
            remains: list[int] = []

            if self.longest_file_frames:
                remains.append(self.longest_file_frames - self.frames_in_this_file)

            if self._sf and self.largest_file_size:
                file_bytes = self.largest_file_size - self.bytes_in_this_file
                remains.append(file_bytes // self.frame_size)

            if remains and min(remains) <= len(b):
                self._close()

            self._sf = self._sf or self._open(offset)
            self._sf.write(b.block)
            offset += len(b)

            self.frames_in_this_file += len(b)
            self.frames_written += len(b)
            self.bytes_in_this_file += len(b) * self.frame_size
