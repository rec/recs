import dataclasses as dc
import sys
import threading
import traceback
import typing as t
from functools import cached_property
from queue import Queue
from threading import Thread

Callback = t.Callable[[], None]


class Event(threading.Event):
    changed: t.List[Callback]

    def __init__(self, *changed: Callback):
        self.changed = list(changed)
        super().__init__()

    def set(self):
        super().set()
        [c() for c in self.changed]

    def clear(self):
        super().clear()
        [c() for c in self.changed]

    def __bool__(self):
        return self.is_set()


class IsRunning:
    def __init__(self):
        self.running = Event()
        self.stopped = Event()

    def start(self):
        self.running.set()

    def stop(self):
        """Stop as soon as possible.
        Might not do anything, should never raise an exception
        """
        self.running.clear()
        self.stopped.set()

    def finish(self):
        """Request an orderly shutdown where all work is finished"""
        self.stop()

    def join(self):
        """Join this thread or process.  Might block indefinitely"""

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


class Runnables(IsRunning):
    runnables: t.Sequence[IsRunning]

    def start(self):
        super().start()
        for r in self.runnables:
            r.stopped.changed.append(self._changed)
            r.start()

    def stop(self):
        self.running.clear()
        for r in self.runnables:
            r.stop()

    def finish(self):
        for r in self.runnables:
            r.finish()

    def join(self):
        for r in self.runnables:
            r.join()

    def _changed(self):
        if sum(bool(r.stopped) for r in self.runnables) == len(self.runnables):
            self.stopped.set()


class IsThread(IsRunning):
    callback: Callback
    name: str = ''

    daemon: bool = False
    looping: bool = False
    stderr: t.TextIO = sys.stderr

    def __str__(self):
        return self.name or self.__class__.__name__

    def new_thread(self) -> Thread:
        return Thread(target=self._target, daemon=self.daemon)

    @cached_property
    def thread(self) -> Thread:
        return self.new_thread()

    def _target(self):
        self.running.set()
        while self.is_running:
            try:
                self.callback()
            except Exception:
                print('', file=self.stderr)
                traceback.print_exc(file=self.stderr)
                self.stop()
                break
            if not self.looping:
                break
        self.stopped.set()

    def start(self):
        self.thread.start()
        self.running.wait()

    def stop(self):
        self.running.clear()

    def finish(self):
        pass


@dc.dataclass
class HasThread(IsThread):
    callback: Callback
    daemon: bool = False
    stderr: t.TextIO = sys.stderr
    looping: bool = False
    name: str = ''

    @property
    def __str__(self):
        return self.name or f'HasThread[{self.callback}]'


@dc.dataclass
class ThreadQueue(Runnables):
    callback: t.Callable[[t.Any], None]
    finish_message: t.Any = None
    maxsize: int = 0
    name: str = 'thread_queue'
    thread_count: int = 1

    @cached_property
    def runnables(self):
        names = [f'ThreadQueue[{self.callback}-i]' for i in range(self.thread_count)]
        return tuple(HasThread(callback=self.target, name=n) for n in names)

    @cached_property
    def queue(self):
        return Queue(self.maxsize)

    def put(self, item):
        self.queue.put_nowait(item)

    def target(self):
        while self.running and (x := self.queue.get()) != self.finish_message:
            self.callback(x)

    def finish(self):
        """Put an empty message into the queue for each listener"""
        for _ in self.runnables:
            self.put(self.finish_message)
