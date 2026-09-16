import threading
from queue import Empty, Queue
from time import monotonic
from typing import NamedTuple

from recs.base import memory
from recs.cfg.cfg import Cfg
from recs.cfg.source import Update
from recs.runtime.source_messages import BufferStats


class BufferedUpdate(NamedTuple):
    update: Update
    start_frame: int
    end_frame: int


class InputBuffer:
    def __init__(self, cfg: Cfg, samplerate: int) -> None:
        self.cfg = cfg
        self.samplerate = samplerate
        self.block_frames = 0
        self.queue: Queue[BufferedUpdate] | None = None
        self.queue_ready = threading.Event()
        self.stats = BufferStats()
        self.timeline_frames = 0
        self.reported_dropped_frames = 0
        self.memory_low = False
        self.last_memory_check = float('-inf')

    def put(self, update: Update) -> None:
        frames = len(update.array)
        if not frames:
            return
        self.block_frames = frames
        start_frame = self.timeline_frames
        self.timeline_frames += frames
        if self._memory_low():
            self._drop(update, frames)
            return
        if self.queue is None:
            maxsize = max(
                1,
                round(
                    self.cfg.recording.audio_buffer_seconds * self.samplerate / frames
                ),
            )
            self.queue = Queue(maxsize=maxsize)
            self.queue_ready.set()
        if self.queue.full():
            self._drop(update, frames)
            return
        buffered = BufferedUpdate(update, start_frame, self.timeline_frames)
        self.queue.put_nowait(buffered)
        self._update_queue_stats()

    def get(
        self, timeout: float | None = None, *, block: bool = True
    ) -> BufferedUpdate:
        if self.queue is None:
            if block:
                self.queue_ready.wait(timeout)
        if self.queue is None:
            raise Empty
        buffered = self.queue.get(block=block, timeout=timeout)
        self.block_frames = max(1, len(buffered.update.array))
        self._update_queue_stats()
        return buffered

    def warnings(self, source_name: str, timestamp: float) -> list[str]:
        warnings: list[str] = []
        if self.stats.dropped_frames > self.reported_dropped_frames:
            dropped = self.stats.dropped_frames - self.reported_dropped_frames
            warnings.append(
                f'Device {source_name}: Dropped {dropped} frames in processing'
            )
            self.reported_dropped_frames = self.stats.dropped_frames

        if self.queue is None:
            return warnings
        return warnings

    def _update_queue_stats(self) -> None:
        if self.queue is None:
            return
        self.stats.queued_blocks = self.queue.qsize()
        self.stats.queued_seconds = (
            self.stats.queued_blocks * self.block_frames / self.samplerate
        )
        self.stats.max_queued_seconds = max(
            self.stats.max_queued_seconds,
            self.stats.queued_seconds,
        )

    def _drop(self, update: Update, frames: int) -> None:
        self.stats.dropped_blocks += 1
        self.stats.dropped_frames += frames
        self.stats.last_drop_timestamp = update.timestamp

    def _memory_low(self) -> bool:
        now = monotonic()
        if now - self.last_memory_check >= self.cfg.recording.memory_check_period:
            self.last_memory_check = now
            available = memory.available_bytes()
            reserve = self.cfg.recording.memory_reserve_megabytes * 1_000_000
            self.memory_low = available is not None and available < reserve
        return self.memory_low
