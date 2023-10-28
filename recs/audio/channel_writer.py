import contextlib
import typing as t
from functools import cached_property
from threading import Lock

from soundfile import SoundFile
from threa import Runnable

from recs import RECS
from recs.misc import legal_filename, recording_path

from ..misc.times import Times
from .block import Block, Blocks
from .file_opener import FileOpener
from .file_types import DTYPE, DType, Format
from .track import Track

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

    def __init__(self, opener: FileOpener, times: Times[int], track: Track) -> None:
        super().__init__()

        self.opener = opener
        self.times = times
        self.track = track
        self._blocks = Blocks()

        self.frame_size = ITEMSIZE[RECS.dtype or DTYPE] * opener.channels
        self.longest_file_frames = times.longest_file_time

        if max_size := SIZE_RESTRICTIONS.get(RECS.format, 0):
            max_frames = (max_size - LARGEST_FRAME) // self.frame_size
            self.longest_file_frames = min(max_frames, self.longest_file_frames)

        self.start()

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

    def _close_file(self):
        if self._sf:
            self._sf.close()
            self._sf = None

    def _close_on_silence(self) -> None:
        removed = self._blocks.clip(self.times.silence_after_end, from_start=False)

        if self._sf and removed:
            self._record(reversed(removed))

        self._close_file()

    def _record(self, blocks: t.Iterable[Block]) -> None:
        def write(a):
            if not self._sf:
                self._sf = self._creator()
                self.files_written += 1
                self.frames_in_this_file = 0

            self._sf.write(a)
            self.blocks_written += 1
            self.frames_in_this_file += len(a)

        for b in blocks:
            remains = self.longest_file_frames - self.frames_in_this_file
            if self.longest_file_frames and remains <= len(b):
                write(b.block[:remains])
                self._close_file()

                if remains == len(b):
                    continue

                b = b[remains:]

            write(b.block)

    def _creator(self) -> SoundFile:
        index = 0
        suffix = ''
        path, name = recording_path.recording_path(self.track)

        while True:
            p = RECS.path / path / legal_filename.legal_filename(name + suffix)
            p.parent.mkdir(exist_ok=True, parents=True)
            try:
                return self.opener.open(p, 'w')
            except FileExistsError:
                index += 1
                suffix = f'_{index}'
