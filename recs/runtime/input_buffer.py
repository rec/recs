import threading
from collections import deque
from collections.abc import Callable
from queue import Empty
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
    uncertain: bool = False


class InputBuffer:
    def __init__(self, cfg: Cfg, samplerate: int) -> None:
        self.cfg = cfg
        self.samplerate = samplerate
        self.queue: deque[BufferedUpdate] = deque()
        self.queued_frames = 0
        self.capacity_frames = max(
            1, round(cfg.recording.audio_buffer_seconds * samplerate)
        )
        self.available = threading.Condition()
        self.stats = BufferStats()
        self.timeline_frames = 0
        self.reported_dropped_frames = 0
        self.memory_low = False
        self.last_memory_check = float('-inf')
        self.forward_audio: Callable[[BufferedUpdate], None] | None = None
        self.check_memory()

    def put(self, update: Update) -> None:
        frames = len(update.array)
        if not frames:
            return
        start_frame = self.timeline_frames
        self.timeline_frames += frames
        if self.memory_low:
            self._drop(update, frames)
            return
        buffered = BufferedUpdate(update, start_frame, self.timeline_frames)
        if self.forward_audio is not None:
            self.forward_audio(buffered)
        with self.available:
            if self.queued_frames + frames > self.capacity_frames:
                self._drop(update, frames)
                return
            self.queue.append(buffered)
            self.queued_frames += frames
            self._update_queue_stats()
            self.available.notify()

    def get(
        self, timeout: float | None = None, *, block: bool = True
    ) -> BufferedUpdate:
        self.check_memory()
        with self.available:
            if not self.queue and (
                not block
                or not self.available.wait_for(lambda: bool(self.queue), timeout)
            ):
                raise Empty
            buffered = self.queue.popleft()
            self.queued_frames -= len(buffered.update.array)
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

        return warnings

    def get_batch(
        self, frames: int, timeout: float | None = None, *, block: bool = True
    ) -> list[BufferedUpdate]:
        self.check_memory()
        result: list[BufferedUpdate] = []
        count = 0
        with self.available:
            if not self.queue and (
                not block
                or not self.available.wait_for(lambda: bool(self.queue), timeout)
            ):
                raise Empty
            while self.queue and count < frames:
                buffered = self.queue.popleft()
                update = buffered.update
                take = min(len(update.array), frames - count)
                if take < len(update.array):
                    end = buffered.start_frame + take
                    result.append(
                        buffered._replace(
                            update=Update(
                                update.array[:take], update.timestamp, update.status
                            ),
                            end_frame=end,
                        )
                    )
                    self.queue.appendleft(
                        buffered._replace(
                            update=Update(
                                update.array[take:],
                                update.timestamp + take / self.samplerate,
                            ),
                            start_frame=end,
                        )
                    )
                else:
                    result.append(buffered)
                count += take
                self.queued_frames -= take
            self._update_queue_stats()
        return result

    def _update_queue_stats(self) -> None:
        self.stats.queued_blocks = len(self.queue)
        self.stats.queued_seconds = self.queued_frames / self.samplerate
        self.stats.max_queued_seconds = max(
            self.stats.max_queued_seconds,
            self.stats.queued_seconds,
        )

    def _drop(self, update: Update, frames: int) -> None:
        self.stats.dropped_blocks += 1
        self.stats.dropped_frames += frames
        self.stats.last_drop_timestamp = update.timestamp

    def check_memory(self) -> None:
        now = monotonic()
        if now - self.last_memory_check >= self.cfg.recording.memory_check_period:
            self.last_memory_check = now
            available = memory.available_bytes()
            reserve = self.cfg.recording.memory_reserve_megabytes * 1_000_000
            self.memory_low = available is not None and available < reserve
