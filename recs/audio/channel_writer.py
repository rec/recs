import contextlib
import typing as t
from datetime import datetime
from pathlib import Path
from threading import Lock

from overrides import override
from soundfile import SoundFile
from threa import Runnable

from recs.base.state import ChannelState
from recs.base.type_conversions import SDTYPE_TO_SUBTYPE, SUBTYPE_TO_SDTYPE
from recs.base.types import SDTYPE, Active, Format, SdType
from recs.cfg import Cfg, Track, source, time_settings
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
    bytes_in_this_file: int = 0

    frames_in_this_file: int = 0
    frames_written: int = 0  # Used elsewhere

    largest_file_size: int = 0
    longest_file_frames: int = 0

    timestamp: float = 0

    _sfs: t.Sequence[SoundFile] = ()

    @property
    def active(self) -> Active:
        return Active.active if self._sfs else Active.inactive

    def __init__(
        self, cfg: Cfg, times: time_settings.TimeSettings[int], track: Track
    ) -> None:
        super().__init__()

        self.cfg = cfg
        self.do_not_record = cfg.dry_run or cfg.calibrate
        self.metadata = cfg.metadata
        self.times = times
        self.track = track

        self._blocks = Blocks()
        self._lock = Lock()

        if track.source.format is None or cfg.cfg.formats:
            self.formats = cfg.formats
        else:
            self.formats = [track.source.format]

        if track.source.subtype is None or cfg.cfg.subtype:
            subtype = cfg.subtype
        else:
            subtype = track.source.subtype

        if track.source.subtype is None or cfg.cfg.sdtype:
            sdtype = cfg.sdtype
        else:
            sdtype = SUBTYPE_TO_SDTYPE[track.source.subtype]

        self.files_written = file_list.FileList()
        self.frame_size = ITEMSIZE[cfg.sdtype or SDTYPE] * len(track.channels)
        self.longest_file_frames = times.longest_file_time

        self.openers = [
            FileOpener(
                channels=len(track.channels),
                format=f,
                samplerate=track.source.samplerate,
                subtype=subtype,
            )
            for f in self.formats
        ]
        self._volume = counter.MovingBlock(times.moving_average_time)

        def size(f: str) -> int:
            return (
                MAX_WAV_SIZE if f == Format.wav and not self.cfg.infinite_length else 0
            )

        self.largest_file_size = max(0, *(size(f) for f in cfg.formats))

    def receive_update(self, update: source.Update) -> ChannelState:
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
        sfs, self._sfs = self._sfs, ()
        for sf in sfs:
            if sf.frames and sf.frames >= self.times.shortest_file_time:
                sf.close()
            else:
                with contextlib.suppress(Exception):
                    sf.close()
                with contextlib.suppress(Exception):
                    Path(sf.name).unlink()

    def _open(self, offset: int) -> t.Sequence[SoundFile]:
        timestamp = self.timestamp - offset / self.track.source.samplerate
        ts = datetime.fromtimestamp(timestamp)

        index = 1 + len(self.files_written)

        metadata = {'date': ts.isoformat(), 'software': URL, 'tracknumber': str(index)}
        metadata |= self.metadata

        self.bytes_in_this_file = max(
            header_size(metadata, f) for f in self.cfg.formats
        )
        self.frames_in_this_file = 0

        path = self.cfg.output_directory.make_path(
            self.track, self.cfg.aliases, timestamp, index
        )
        sfs = [o.create(metadata, path) for o in self.openers]
        self.files_written.extend(Path(sf.name) for sf in sfs)
        return sfs

    def _receive_block(self, block: Block, timestamp: float) -> ChannelState:
        saved_state = self._state(
            max_amp=max(block.max) / block.scale,
            min_amp=min(block.min) / block.scale,
        )

        dt = self.timestamp - timestamp
        self.timestamp = timestamp
        self._volume(block)

        if not self.do_not_record and (self._sfs or not self.stopped):
            expected_dt = len(block) / self.track.source.samplerate

            if dt > expected_dt * BLOCK_FUZZ:  # We were asleep, or otherwise lost time
                self._write_and_close()

            self._blocks.append(block)

            if (
                self.times.record_everything
                or block.volume >= self.times.noise_floor_amplitude
            ):
                if not self._sfs:  # Record some quiet before the first block
                    length = self.times.quiet_before_start + len(self._blocks[-1])
                    self._blocks.clip(length, from_start=True)

                self._write_blocks(self._blocks)
                self._blocks.clear()

            if self.stopped or self._blocks.duration > self.times.stop_after_quiet:
                self._write_and_close()

        return self._state() - saved_state

    def _state(self, **kwargs: t.Any) -> ChannelState:
        return ChannelState(
            file_count=len(self.files_written),
            file_size=self.files_written.total_size,
            is_active=bool(self._sfs),
            recorded_time=self.frames_written / self.track.source.samplerate,
            timestamp=self.timestamp,
            volume=tuple(self._volume.mean()),
            **kwargs,
        )

    def _write_and_close(self) -> None:
        # Record some quiet after the last block
        removed = self._blocks.clip(self.times.quiet_after_end, from_start=False)

        if self._sfs and removed:
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

            if self._sfs and self.largest_file_size:
                file_bytes = self.largest_file_size - self.bytes_in_this_file
                remains.append(file_bytes // self.frame_size)

            if remains and min(remains) <= len(b):
                self._close()

            self._sfs = self._sfs or self._open(offset)
            for sf in self._sfs:
                sf.write(b.block)
            offset += len(b)

            self.frames_in_this_file += len(b)
            self.frames_written += len(b)
            self.bytes_in_this_file += len(b) * self.frame_size
