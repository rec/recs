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

HEADER_SIZE = 0x58
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
DETECT_SLEEP = False


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

            if self._blocks:
                self._record(self._blocks)
                self._blocks.clear()

            if self._sf:
                self._sf.close()
                self._sf = None

            self.stopped.set()

    def write(self, block: Block, time: float) -> None:
        block_size = len(block)

        self.frames_seen += block_size
        self.blocks_seen += 1

        if self.dry_run or not (self.running or self._sf):
            return

        dt = self.time - time
        expected_dt = block_size / self.track.device.samplerate

        with self._lock:
            if DETECT_SLEEP and dt > expected_dt * BLOCK_FUZZ:
                # We were asleep, or otherwise lost time.
                self._close_on_silence()

            self._blocks.append(block)

            if self._blocks[-1].volume >= self.times.noise_floor_amplitude:
                self._record_on_not_silence()

            elif self._blocks.duration > self.times.stop_after_silence:
                self._close_on_silence()

            if not self.running:
                self._close_on_silence()

        self.time = time

    def _close_file(self):
        if self._sf:
            self._sf.close()
            if self._sf.frames <= self.times.shortest_file_time:
                if (p := Path(self._sf.name)).exists():
                    p.unlink()
            self._sf = None

    def _close_on_silence(self) -> None:
        removed = self._blocks.clip(self.times.silence_after_end, from_start=False)

        if self._sf and removed:
            self._record(reversed(removed))

        self._close_file()

    def _record(self, blocks: t.Iterable[Block]) -> None:
        for b in blocks:
            # Check if this block will overrun the file size or length
            remains: list[int] = []

            if self.longest_file_frames:
                remains.append(self.longest_file_frames - self.frames_in_this_file)

            if self.largest_file_size and self._sf:
                bytes_remaining = self.largest_file_size - self._sf.tell()
                remains.append(bytes_remaining // self.frame_size)

            if remains and (r := min(remains)) <= len(b):
                self._write(b[:r])
                self._close_file()
                b = b[r:]

            self._write(b)

    def _record_on_not_silence(self) -> None:
        if not self._sf:
            length = self.times.silence_before_start + len(self._blocks[-1])
            self._blocks.clip(length, from_start=True)

        self._record(self._blocks)
        self._blocks.clear()

    def _write(self, b: Block) -> None:
        if not b:
            return

        if not self._sf:
            self._sf = self.opener.create()

            if self.largest_file_size:
                self._sf.flush()
                self.bytes_in_this_file = self._sf.tell()

            self.files_written.append(Path(self._sf.name))
            self.frames_in_this_file = 0

        self._sf.write(b.block)

        self.blocks_written += 1
        self.frames_in_this_file += len(b)
        self.frames_written += len(b)

        if self.largest_file_size:
            self.bytes_in_this_file += len(b) * self.frame_size
