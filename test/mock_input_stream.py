import random
from test.conftest import SLEEP_TIME

import numpy as np
import sounddevice as sd
from threa import HasThread

from recs.base import times


class InputStream(sd.InputStream):
    BLOCK_SIZE = 0x80

    def __init__(self, **ka):
        for k, v in ka.items():
            try:
                setattr(self, k, v)
            except AttributeError:
                setattr(self, '_' + k, v)

        self._recs_count = 0

        seed = int.from_bytes(self.device.encode(), byteorder='big')
        self._recs_random = random.Random(seed)
        self._recs_thread = HasThread(
            self._recs_callback, looping=True, name=f'Thread-{self.device}'
        )

        shape = self.BLOCK_SIZE, self.channels
        rng = np.random.default_rng(seed)
        array = rng.uniform(-1 / 16, 1 / 16, size=shape)
        assert self.dtype == 'float32'
        assert array.dtype == np.double

        self._recs_array = array.astype(self.dtype)

    def start(self) -> None:
        self._recs_thread.start()

    def stop(self, ignore_errors: bool = True) -> None:
        self._recs_thread.stop()

    def close(self, ignore_errors: bool = True) -> None:
        self.stop()

    def _recs_callback(self) -> None:
        self.callback(self._recs_array, self.BLOCK_SIZE, 0, 0)
        times.sleep(SLEEP_TIME * self._recs_random.uniform(0.8, 1.2))
