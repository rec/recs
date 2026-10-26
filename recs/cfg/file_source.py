from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast, override

import soundfile
from threa import HasThread, Runnable
from ufor.encoding import Format, Subtype

from recs.base.errors import RecsError
from recs.base.types import SdType

from .source import Source, Update, to_matrix

BLOCKSIZE = 0x1000


class FileSource(Source):
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            with self._stream() as fp:
                self.format = Format(fp.format.lower())
                self.subtype = Subtype(fp.subtype.lower())
                super().__init__(
                    channels=fp.channels,
                    format=self.format,
                    name=path.as_posix(),
                    samplerate=int(fp.samplerate),
                    subtype=self.subtype,
                )
        except (OSError, soundfile.SoundFileError, ValueError) as error:
            raise RecsError(f'Cannot read audio input {path}: {error}') from None

    def _stream(self) -> soundfile.SoundFile:
        return soundfile.SoundFile(file=self.path, mode='r')

    @override
    def input_stream(
        self, sdtype: SdType, update_callback: Callable[[Update], None]
    ) -> Runnable:
        result: Runnable

        def input_stream() -> None:
            try:
                with self._stream() as fp:
                    timestamp = 0
                    dtype = cast(Literal['float32', 'int32', 'int16'], sdtype)
                    # Own bounded read chunks, rather than views retaining a
                    # potentially gigabyte-sized decoded batch in the queue.
                    for block in fp.blocks(BLOCKSIZE, dtype=dtype):
                        block = to_matrix(block)
                        update_callback(Update(block, timestamp / self.samplerate))
                        timestamp += len(block)
            finally:
                result.stop()

        return (result := HasThread(input_stream))
