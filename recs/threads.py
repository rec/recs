from functools import cached_property
from queue import Queue
from threading import Lock, Thread
import dataclasses as dc
import sys
import traceback
import typing as t


class IsRunning:
    running = False

    @cached_property
    def _lock(self):
        return Lock()

    def start(self):
        with self._lock:
            if self.running:
                return True
            self.running = True

        self._start()

    def _start(self):
        pass

    def stop(self):
        # Might not do anything, should never raise an exception
        self.running = False


@dc.dataclass
class HasThread(IsRunning):
    callback: t.Callable[[], t.Any]
    daemon: bool = True
    stderr: t.TextIO = sys.stderr
    looping: bool = False

    @property
    def name(self):
        return self.__class__.__name__

    def new_thread(self) -> Thread:
        return Thread(target=self._target, daemon=self.daemon)

    @cached_property
    def thread(self) -> Thread:
        return self.new_thread()

    def _target(self):
        while self.running:
            try:
                self.callback()
            except Exception:
                traceback.print_exc(file=self.stderr)
                self.stop()
                raise
            else:
                if not self.looping:
                    break

    def _start(self):
        self.thread.start()


@dc.dataclass
class ThreadQueue(IsRunning):
    callback: t.Callable[[t.Any], t.Any]
    finish_message: t.Any = None
    maxsize: int = 0
    name: str = 'thread_queue'
    thread_count: int = 1

    def _start(self):
        [t.start() for t in self.threads]

    @cached_property
    def queue(self):
        return Queue(self.maxsize)

    def put(self, item):
        self.queue.put_nowait(item)

    @cached_property
    def threads(self):
        return tuple(self.new_thread() for i in range(self.thread_count))

    def target(self):
        while self.running and (x := self.queue.get()) != self.finish_message:
            self.callback(x)

    def join(self):
        for th in self.threads:
            th.join()

    def start(self):
        super().start()
        for th in self.threads:
            th.start()

    def stop(self):
        super().stop()
        for th in self.threads:
            th.stop()

    def finish(self):
        for th in self.threads:
            self.put(self.finish_message)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.finish()
                self.join()
        finally:
            self.stop()

    def run_to_finish(self):
        self.start()
        self.finish()
        try:
            self.join()
        except Exception:
            self.stop()
