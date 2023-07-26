from functools import cached_property
from queue import Queue
from threading import Lock
from threading import Thread
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
        # Might not do anything.
        self.running = False


class HasThread(IsRunning):
    _target = None
    daemon = True
    looping = False

    @property
    def name(self):
        return self.__class__.__name__

    def _thread_target(self):
        while self.running:
            try:
                self._target()
            except Exception as e:
                print('Exception', self, self.name, e, file=sys.stderr)
                traceback.print_stack()
                self.stop()
                raise
            else:
                if not self.looping:
                    break

    def new_thread(self, run_loop=False):
        return Thread(target=self._thread_target, daemon=self.daemon)

    @cached_property
    def thread(self):
        return self.new_thread()

    def _start(self):
        self.thread.start()


class ThreadQueue(HasThread):
    maxsize = 0
    thread_count = 1
    callback = print
    thread = None
    name = 'thread_queue'

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

    def _target(self):
        while self.running and (item := self.queue.get()) is not None:
            self.callback(item)
