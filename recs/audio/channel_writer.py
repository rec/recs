import contextlib
import typing as t
from functools import cached_property
from threading import Lock

from soundfile import SoundFile
from threa import Runnable

from recs import RECS

from ..misc.times import Times
from .block import Block, Blocks
from .file_creator import FileCreator
from .file_types import DTYPE, DType, Format

LARGEST_FRAME = 0x100
SIZE_RESTRICTIONS = {
    Format.aiff: 0x8000_0000,
    Format.wav: 0x1_0000_0000,
}
ITEMSIZE = {
    DType.float32: 4,
    DType.float64: 8,
    DType.int16: 2,
    DType.int32: 4,
}


class ChannelWriter(Runnable):
    blocks_written: int = 0
    files_written: int = 0
    frames_in_this_file: int = 0
    frames_seen: int = 0

    _sf: SoundFile | None = None

    def __init__(self, creator: FileCreator, times: Times[int]) -> None:
        super().__init__()
        self.start()

        self.creator = creator
        self.times = times
        self._blocks = Blocks()

        self.frame_size = ITEMSIZE[RECS.dtype or DTYPE] * creator.opener.channels
        self.longest_file_frames = times.longest_file_time

        if max_size := SIZE_RESTRICTIONS.get(RECS.format, 0):
            max_frames = (max_size - LARGEST_FRAME) // self.frame_size
            self.longest_file_frames = min(max_frames, self.longest_file_frames)

    def write(self, block: Block) -> None:
        with self._lock:
            if not (self.running or self._sf):
                return

            self.frames_seen += len(block)
            self._blocks.append(block)

            if self._blocks[-1].volume >= self.times.noise_floor_amplitude:
                self._record_on_not_silence()

            elif self._blocks.duration > self.times.stop_after_silence:
                self._close_on_silence()

            if not self.running:
                self._close_on_silence()
                return

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

    @cached_property
    def _lock(self):
        if RECS.use_locking:
            return Lock()
        return contextlib.nullcontext()

    def _record_on_not_silence(self) -> None:
        if not self._sf:
            length = self.times.silence_before_start + len(self._blocks[-1])
            self._blocks.clip(length, from_start=True)

        self._record(self._blocks)
        self._blocks.clear()

    def _close_on_silence(self) -> None:
        removed = self._blocks.clip(self.times.silence_after_end, from_start=False)

        if self._sf:
            if removed:
                self._record(reversed(removed))

            self._sf.close()
            self._sf = None

    def _record(self, blocks: t.Iterable[Block]) -> None:
        def write(a):
            self._sf.write(a)
            self.blocks_written += 1

        for b in blocks:
            remains = self.longest_file_frames - self.frames_in_this_file
            if self.longest_file_frames and remains <= len(b):
                assert self._sf, 'Tiny file length'
                write(b.block[:remains])

                self._sf.close()
                self._sf = None

                if remains == len(b):
                    continue

                b = b[remains:]

            if not self._sf:
                self._sf = self.creator()
                self.files_written += 1
                self.frames_in_this_file = 0

            self._sf.write(b.block)
            self.frames_in_this_file += len(b)
            self.blocks_written += 1
