import abc
import dataclasses as dc
import sys
import threading
import traceback
import typing as t
from functools import cached_property, partial
from queue import Queue
from threading import Thread

Callback = t.Callable[[], None]
print_err = partial(print, file=sys.stderr)


class Event(threading.Event):
    """
    A threading.Event that also calls back to zero or more functions when its state
    is set, and has a __bool__ method.

    Note that the callback might happen on some completely different thread,
    so these functions cannot block"""

    on_set: t.List[Callback]

    def __init__(self, *on_set: Callback):
        self.on_set = list(on_set)
        super().__init__()

    def set(self):
        super().set()
        [c() for c in self.on_set]

    def clear(self):
        super().clear()
        [c() for c in self.on_set]

    def __bool__(self):
        return self.is_set()


class IsRunning:
    """A base class for things that start, run, finish, stop and join

    An IsRunning can also be used as a context manager:

        with my_thread:
            do_stuff()

    means the same as

        my_thread.start()
        try:
            do_stuff()
            my_thread.finish()
            my_thread.join()
        finally:
            my_thread.stop()

    """

    #: An Event that is set once this object is actually running
    running: Event

    #: An event that is set once this object is fully stopped
    stopped: Event

    def __init__(self):
        self.running = Event()
        self.stopped = Event()

    def start(self):
        """Start this object.

        Note that self.running might not be immediately true after this method completes
        """
        self.running.set()

    def stop(self):
        """Stop as soon as possible. might not do anything, should never raise.

        Note that self.stopped might not be immediately true after this method completes
        """
        self.running.clear()
        self.stopped.set()

    def finish(self):
        """Request an orderly shutdown where all existing work is completed.

        Note that self.stopped might not be immediately true after this method completes
        """
        self.stop()

    def join(self, timeout: t.Optional[float] = None):
        """Join this thread or process.  Might block indefinitely, might do nothing"""

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
    """Collect zero or more IsRunning into one"""

    runnables: t.Sequence[IsRunning]

    def start(self):
        super().start()
        for r in self.runnables:
            r.stopped.on_set.append(self._on_set)
            r.start()

    def stop(self):
        self.running.clear()
        for r in self.runnables:
            r.stop()

    def finish(self):
        for r in self.runnables:
            r.finish()

    def join(self, timeout: t.Optional[float] = None):
        for r in self.runnables:
            r.join(timeout)

    def _on_set(self):
        if sum(bool(r.stopped) for r in self.runnables) == len(self.runnables):
            self.stopped.set()


class ThreadBase(IsRunning):
    """A base class for classes with a thread.

    It adds the following features to threading.Thread:

    * Has Events `running` and `stopped` with `on_set` callbacks
    * Handles exceptions and prints or redirects them
    * Runs once, or multiple times, depending on `self.looping`

    """

    callback: Callback = staticmethod(print)
    daemon: bool = False
    error: t.Callable = staticmethod(print_err)
    looping: bool = False
    name: str = ''

    def __str__(self):
        return self.name or self.__class__.__name__

    def run(self):
        self.running.set()
        while self.is_running:
            try:
                self.callback()
            except Exception:
                self.error('Exception in', self)
                self.error(traceback.format_exc())
                self.stop()
            else:
                if not self.looping:
                    break
        self.stopped.set()

    def stop(self):
        self.running.clear()

    def finish(self):
        pass


class IsThread(ThreadBase, Thread):
    """This ThreadBase inherits from threading.Thread.

    To use IsThread, derive from it and override self.callback()
    """

    @abc.abstractmethod
    def callback(self):
        pass

    def start(self):
        ThreadBase.start(self)


@dc.dataclass
class HasThread(ThreadBase):
    """This ThreadBase contains a thread, and is constructed with a callback"""

    callback: Callback = print
    daemon: bool = False
    error: t.Callable = print_err
    looping: bool = False
    name: str = ''

    def start(self):
        self.thread.start()

    def new_thread(self) -> Thread:
        return Thread(target=self.run, daemon=self.daemon)

    @cached_property
    def thread(self) -> Thread:
        return self.new_thread()

    @property
    def __str__(self):
        return self.name or f'HasThread[{self.callback}]'


@dc.dataclass
class ThreadQueue(Runnables):
    """A simple multi-producer, multi-consumer queue with one thread per consumer.

    There is a special `finish_message` value, which when received shuts down
    that consumer.  ThreadQueue.finish() puts one `self.finish_message` onto the
    queue for each consumer.
    """

    callback: t.Callable[[t.Any], None]
    finish_message: t.Any = None
    maxsize: int = 0
    name: str = 'thread_queue'
    thread_count: int = 1

    pass_self = True

    @cached_property
    def runnables(self):
        return tuple(self._thread(i) for i in range(self.thread_count))

    @cached_property
    def queue(self):
        return Queue(self.maxsize)

    def put(self, item):
        self.queue.put_nowait(item)

    def _thread(self, i: int) -> HasThread:
        t = HasThread(name=f'ThreadQueue[{self.callback}-{i}]')
        t.callback = lambda: self._run(t)
        return t

    def _run(self, thread: HasThread):
        try:
            while self.running and (x := self.queue.get()) != self.finish_message:
                self.callback(x)
        finally:
            thread.stop()

    def finish(self):
        """Put an empty message into the queue for each listener"""
        for _ in self.runnables:
            self.put(self.finish_message)
