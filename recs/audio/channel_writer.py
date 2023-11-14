import typing as t
from pathlib import Path
from threading import Lock

from soundfile import SoundFile
from threa import Runnable

from recs.base.cfg import Cfg
from recs.base.types import SDTYPE, Format, SdType
from recs.misc import file_list

from ..base import times
from .block import Block, Blocks
from .file_opener import FileOpener
from .track import Track

FORMAT_TO_SIZE_LIMIT = {
    Format.aiff: 0x8000_0000,
    Format.wav: 0x1_0000_0000,
}
ITEMSIZE = {
    SdType.float32: 4,
    SdType.int16: 2,
    SdType.int24: 3,
    SdType.int32: 4,
}
BLOCK_FUZZ = 2


class ChannelWriter(Runnable):
    blocks_seen: int = 0
    blocks_written: int = 0
    bytes_in_this_file: int = 0

    frames_in_this_file: int = 0
    frames_seen: int = 0
    frame_size: int = 0
    frames_written: int = 0

    largest_file_size: int = 0
    longest_file_frames: int = 0

    time: float = 0
    tracknumber: int = 0

    _sf: SoundFile | None = None

    @property
    def active(self) -> bool:
        return bool(self._sf)

    def __init__(self, cfg: Cfg, times: times.Times[int], track: Track) -> None:
        super().__init__()

        self.dry_run = cfg.dry_run
        self.times = times
        self.track = track

        self._blocks = Blocks()
        self._lock = Lock()

        self.files_written = file_list.FileList()
        self.frame_size = ITEMSIZE[cfg.sdtype or SDTYPE] * len(track.channels)
        self.longest_file_frames = times.longest_file_time
        self.opener = FileOpener(cfg, track)

        if not cfg.infinite_length:
            self.largest_file_size = FORMAT_TO_SIZE_LIMIT.get(cfg.format, 0)

    def stop(self) -> None:
        with self._lock:
            self.running.clear()
            self._write_and_close()
            self.stopped.set()

    def write(self, block: Block, time: float) -> None:
        self.frames_seen += len(block)
        self.blocks_seen += 1

        if not self.dry_run and (self.running or self._sf):
            dt = self.time - time
            self.time = time

            with self._lock:
                self._write(block, dt)

    def _write(self, block: Block, dt: float):
        expected_dt = len(block) / self.track.device.samplerate

        if dt > expected_dt * BLOCK_FUZZ:
            # We were asleep, or otherwise lost time.
            self._write_and_close()

        self._blocks.append(block)

        if block.volume >= self.times.noise_floor_amplitude:
            if not self._sf:
                # Record a little quiet before the first block
                length = self.times.quiet_before_start + len(self._blocks[-1])
                self._blocks.clip(length, from_start=True)

            self._write_blocks(self._blocks)
            self._blocks.clear()

        if not self.running or self._blocks.duration > self.times.stop_after_quiet:
            self._write_and_close()

    def _write_and_close(self) -> None:
        # Record a little quiet after the last block
        removed = self._blocks.clip(self.times.quiet_after_end, from_start=False)

        if self._sf and removed:
            self._write_blocks(reversed(removed))

        self._close()

    def _close(self) -> None:
        if self._sf:
            self._sf.close()
            if self._sf.frames <= self.times.shortest_file_time:
                if (p := Path(self._sf.name)).exists():
                    p.unlink()
            self._sf = None

    def _write_blocks(self, blocks: t.Iterable[Block]) -> None:
        for b in blocks:
            # Check if this block will overrun the file size or length
            remains: list[int] = []

            if self.longest_file_frames:
                remains.append(self.longest_file_frames - self.frames_in_this_file)

            if self.largest_file_size and self._sf:
                file_frames = self.largest_file_size // self.frame_size
                remains.append(file_frames - self._sf.frames)

            if remains and (r := min(remains)) <= len(b):
                self._write_one(b[:r])
                self._close()
                b = b[r:]

            if b:
                self._write_one(b)

    def _write_one(self, b: Block) -> None:
        if not self._sf:
            self.tracknumber += 1
            self._sf = self.opener.create(self.tracknumber)

            self.files_written.append(Path(self._sf.name))
            self.frames_in_this_file = 0

        self._sf.write(b.block)

        self.blocks_written += 1
        self.frames_in_this_file += len(b)
        self.frames_written += len(b)

        if self.largest_file_size:
            self.bytes_in_this_file += len(b) * self.frame_size
