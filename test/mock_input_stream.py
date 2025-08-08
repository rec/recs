import random
from test.conftest import BLOCK_SIZE, SLEEP_TIME

import numpy as np
import sounddevice
from threa import HasThread

from recs.base import times

AMPLITUDE = 1 / 16


class InputStreamBase(sounddevice.InputStream):
    def __init__(self, **ka):
        for k, v in ka.items():
            try:
                setattr(self, k, v)
            except AttributeError:
                setattr(self, '_' + k, v)

        self.actions = []
        self.seed = int.from_bytes(self.device.encode(), byteorder='big')

        shape = BLOCK_SIZE, self.channels
        rng = np.random.default_rng(self.seed)
        array = rng.uniform(-AMPLITUDE, AMPLITUDE, size=shape)
        self._recs_array = array.astype(self.dtype)

    def _recs_callback(self) -> None:
        self.callback(self._recs_array, BLOCK_SIZE, 0, 0)


class ThreadInputStream(InputStreamBase):
    def __init__(self, **ka):
        super().__init__(**ka)

        self._recs_random = random.Random(self.seed)
        self._recs_thread = HasThread(
            self._recs_callback, looping=True, name=f'Thread-{self.device}'
        )

    def start(self) -> None:
        self._recs_thread.start()

    def stop(self, ignore_errors: bool = True) -> None:
        self._recs_thread.stop()

    def close(self, ignore_errors: bool = True) -> None:
        self.stop()

    def _recs_callback(self) -> None:
        super()._recs_callback()
        times.sleep(SLEEP_TIME * self._recs_random.uniform(0.8, 1.2))


class InputStreamReporter(InputStreamBase):
    def __init__(self, **ka):
        super().__init__(**ka)
        self._recs_report = []

    def start(self) -> None:
        return self._recs_report.append('start')

    def stop(self, ignore_errors: bool = True) -> None:
        return self._recs_report.append('stop')

    def close(self, ignore_errors: bool = True) -> None:
        return self._recs_report.append('close')

    def _recs_callback(self) -> None:
        super()._recs_callback()
        self._recs_report.append('message_callback')
