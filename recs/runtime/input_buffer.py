import sys
import threading
from collections import deque
from collections.abc import Callable
from queue import Empty
from time import monotonic, perf_counter
from typing import NamedTuple

import numpy as np

from recs.base import memory
from recs.cfg.cfg import Cfg
from recs.cfg.source import Update
from recs.runtime.source_messages import BufferStats


class BufferedUpdate(NamedTuple):
    update: Update
    start_frame: int
    end_frame: int
    uncertain: bool = False


class QueuedUpdate(NamedTuple):
    buffered: BufferedUpdate
    arrived_at: float
    owner: int
    overhead: int


class InputBuffer:
    def __init__(self, cfg: Cfg, samplerate: int) -> None:
        self.cfg = cfg
        self.samplerate = samplerate
        self.queue: deque[QueuedUpdate] = deque()
        self.owners: dict[int, tuple[int, int]] = {}
        self.queued_bytes = 0
        self.queued_memory_bytes = 0
        self.max_queued_memory_bytes = 0
        self.capacity_bytes = cfg.recording.audio_buffer_megabytes * 1_000_000
        self.max_queued_frames = 0
        self.callback_count = 0
        self.callback_frames_min = 0
        self.callback_frames_max = 0
        self.histogram: dict[int, int] = {}
        self.callback_seconds = 0.0
        self.max_callback_seconds = 0.0
        self.dropped_blocks = 0
        self.dropped_frames = 0
        self.dropped_byte_limit_frames = 0
        self.dropped_memory_frames = 0
        self.last_drop_timestamp = 0.0
        self.unknown_losses: list[tuple[int, float]] = []
        self.queued_frames = 0
        self.capacity_frames = max(
            1, round(cfg.recording.audio_buffer_seconds * samplerate)
        )
        self.available = threading.Condition()
        self.timeline_frames = 0
        self.reported_dropped_frames = 0
        self.memory_low = False
        self.last_memory_check = float('-inf')
        self.forward_audio: Callable[[BufferedUpdate], None] | None = None
        self.check_memory()

    @property
    def stats(self) -> BufferStats:
        with self.available:
            values = dict(
                callback_count=self.callback_count,
                callback_frames_min=self.callback_frames_min,
                callback_frames_max=self.callback_frames_max,
                callback_frame_histogram={
                    str(1 << k) + ('-' + str((1 << (k + 1)) - 1) if k else ''): v
                    for k, v in self.histogram.items()
                },
                received_frames=self.timeline_frames,
                callback_seconds=self.callback_seconds,
                max_callback_seconds=self.max_callback_seconds,
                queued_blocks=len(self.queue),
                queued_seconds=self.queued_frames / self.samplerate,
                max_queued_seconds=self.max_queued_frames / self.samplerate,
                queued_bytes=self.queued_bytes,
                queued_memory_bytes=self.queued_memory_bytes,
                max_queued_memory_bytes=self.max_queued_memory_bytes,
                oldest_buffer_seconds=max(
                    0.0, perf_counter() - self.queue[0].arrived_at
                )
                if self.queue
                else 0.0,
                dropped_blocks=self.dropped_blocks,
                dropped_frames=self.dropped_frames,
                dropped_byte_limit_frames=self.dropped_byte_limit_frames,
                dropped_memory_frames=self.dropped_memory_frames,
                last_drop_timestamp=self.last_drop_timestamp,
            )
        return BufferStats.model_validate(values)

    def take_unknown_losses(self) -> list[tuple[int, float]]:
        with self.available:
            result, self.unknown_losses = self.unknown_losses, []
        return result

    def put(self, update: Update) -> None:
        started = perf_counter()
        frames = len(update.array)
        if not frames:
            return
        start_frame = self.timeline_frames
        self.timeline_frames += frames
        if 'input overflow' in update.status:
            with self.available:
                self.unknown_losses.append((start_frame, update.timestamp))
        if self.memory_low:
            with self.available:
                self.dropped_memory_frames += frames
                self._drop(update, frames)
                self._record_callback(frames, started, update.copy_seconds)
            return
        buffered = BufferedUpdate(update, start_frame, self.timeline_frames)
        if self.forward_audio is not None:
            self.forward_audio(buffered)
        array = update.array
        owner = array
        while isinstance(owner.base, np.ndarray):
            owner = owner.base
        owner_id = id(owner)
        owner_size = sys.getsizeof(owner) + (
            owner.nbytes if owner.base is not None else 0
        )
        # Reserve an array-view header even before a consumer splits this entry.
        overhead = (
            sys.getsizeof(buffered)
            + sys.getsizeof(update)
            + sys.getsizeof(started)
            + sys.getsizeof(start_frame)
            + sys.getsizeof(self.timeline_frames)
            + sys.getsizeof(array)
            - (array.nbytes if array.flags.owndata else 0)
            + sys.getsizeof(QueuedUpdate(buffered, started, owner_id, 0))
        )
        with self.available:
            added = overhead + (0 if owner_id in self.owners else owner_size)
            byte_limit = self.queued_memory_bytes + added > self.capacity_bytes
            if self.queued_frames + frames > self.capacity_frames or byte_limit:
                if byte_limit:
                    self.dropped_byte_limit_frames += frames
                self._drop(update, frames)
            else:
                count, size = self.owners.get(owner_id, (0, owner_size))
                self.owners[owner_id] = (count + 1, size)
                self.queue.append(QueuedUpdate(buffered, started, owner_id, overhead))
                self.queued_frames += frames
                self.queued_bytes += array.nbytes
                self.queued_memory_bytes += added
                self.max_queued_memory_bytes = max(
                    self.max_queued_memory_bytes, self.queued_memory_bytes
                )
                self.max_queued_frames = max(self.max_queued_frames, self.queued_frames)
                self.available.notify()
            self._record_callback(frames, started, update.copy_seconds)

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
            entry = self.queue.popleft()
            buffered = entry.buffered
            self.queued_frames -= len(buffered.update.array)
            self.queued_bytes -= buffered.update.array.nbytes
            self._release(entry)
            return buffered

    def warnings(self, source_name: str, timestamp: float) -> list[str]:
        warnings: list[str] = []
        if self.dropped_frames > self.reported_dropped_frames:
            dropped = self.dropped_frames - self.reported_dropped_frames
            warnings.append(
                f'Device {source_name}: Dropped {dropped} frames in processing'
            )
            self.reported_dropped_frames = self.dropped_frames

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
                entry = self.queue.popleft()
                buffered = entry.buffered
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
                    remainder = buffered._replace(
                        update=Update(
                            update.array[take:],
                            update.timestamp + take / self.samplerate,
                        ),
                        start_frame=end,
                    )
                    self.queue.appendleft(entry._replace(buffered=remainder))
                else:
                    result.append(buffered)
                    self._release(entry)
                count += take
                self.queued_frames -= take
                self.queued_bytes -= (
                    take
                    * update.array.dtype.itemsize
                    * (update.array.shape[1] if update.array.ndim > 1 else 1)
                )
        return result

    def _release(self, entry: QueuedUpdate) -> None:
        count, size = self.owners[entry.owner]
        self.queued_memory_bytes -= entry.overhead
        if count == 1:
            del self.owners[entry.owner]
            self.queued_memory_bytes -= size
        else:
            self.owners[entry.owner] = (count - 1, size)

    def _record_callback(
        self, frames: int, started: float, copy_seconds: float
    ) -> None:
        self.callback_count += 1
        self.callback_frames_min = (
            min(self.callback_frames_min, frames)
            if self.callback_frames_min
            else frames
        )
        self.callback_frames_max = max(self.callback_frames_max, frames)
        bucket = frames.bit_length() - 1
        self.histogram[bucket] = self.histogram.get(bucket, 0) + 1
        elapsed = perf_counter() - started + copy_seconds
        self.callback_seconds += elapsed
        self.max_callback_seconds = max(self.max_callback_seconds, elapsed)

    def _drop(self, update: Update, frames: int) -> None:
        self.dropped_blocks += 1
        self.dropped_frames += frames
        self.last_drop_timestamp = update.timestamp

    def check_memory(self) -> None:
        now = monotonic()
        if now - self.last_memory_check >= self.cfg.recording.memory_check_period:
            self.last_memory_check = now
            available = memory.available_bytes()
            reserve = self.cfg.recording.memory_reserve_megabytes * 1_000_000
            self.memory_low = available is not None and available < reserve
