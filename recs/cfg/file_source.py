import traceback
import typing as t
from pathlib import Path

import soundfile
from overrides import override
from threa import HasThread, Runnable

from recs.base.types import Format, SdType, Stop, Subtype

from .source import Source, Update, to_matrix

BLOCKSIZE = 0x1000
BLOCKCOUNT = 0x1000


class FileSource(Source):
    def __init__(self, path: Path) -> None:
        self.path = path
        assert self.path.exists()

        with self._stream() as fp:
            self.format = Format(fp.format.lower())
            self.subtype = Subtype(fp.subtype.lower())
            super().__init__(
                channels=fp.channels,
                format=self.format,
                name=str(path),
                samplerate=int(fp.samplerate),
                subtype=self.subtype,
            )

    def _stream(self) -> soundfile.SoundFile:
        return soundfile.SoundFile(file=self.path, mode='r')

    @override
    def input_stream(
        self, sdtype: SdType, update_callback: t.Callable[[Update], None]
    ) -> Runnable:
        result: Runnable

        def input_stream() -> None:
            try:
                with self._stream() as fp:
                    timestamp = 0
                    for block in fp.blocks(BLOCKSIZE * BLOCKCOUNT):
                        block = to_matrix(block)
                        for i in range(BLOCKCOUNT):
                            array = block[i * BLOCKSIZE : (i + 1) * BLOCKSIZE]
                            if not array.size:
                                break
                            update_callback(Update(array, timestamp / self.samplerate))
                            timestamp += BLOCKSIZE

            except Exception:
                traceback.print_exc()

            finally:
                result.stop()

        return (result := HasThread(input_stream))
