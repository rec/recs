import typing as t
from pathlib import Path

import soundfile as sf
from overrides import override
from threa import HasThread, Runnable

from recs.base.types import SdType, Stop

from .source import Source, Update

BLOCKSIZE = 0x1000
BLOCKCOUNT = 0x1000


class FileSource(Source):
    def __init__(self, name: str) -> None:
        self.path = Path(name)
        assert self.path.exists()

        with self._stream() as fp:
            self.format = fp.format.lower()
            super().__init__(
                channels=fp.channels, name=name, samplerate=int(fp.samplerate)
            )
            self.subtype = fp.subtype

    def _stream(self) -> sf.SoundFile:
        return sf.SoundFile(file=self.path, mode='r')

    @override
    def input_stream(
        self,
        on_error: Stop,
        sdtype: SdType,
        update_callback: t.Callable[[Update], None],
    ) -> Runnable:
        def input_stream() -> None:
            try:
                with self._stream() as fp:
                    timestamp = 0
                    for block in fp.blocks(BLOCKSIZE * BLOCKCOUNT):
                        for i in range(BLOCKCOUNT):
                            array = block[i * BLOCKSIZE : (i + 1) * BLOCKSIZE, :]
                            update_callback(Update(array, timestamp / self.samplerate))
                            timestamp += BLOCKSIZE

            except Exception:
                on_error()

        return HasThread(input_stream)
