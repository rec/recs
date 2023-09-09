import dataclasses as dc
from pathlib import Path

import numpy as np
import tdir

from recs import array
from recs.audio import file_format as ff
from recs.audio import file_writer as fw
from recs.audio.silence import SilenceStrategy

I, O = [array((1, -1, 1, -1))], [array((0, 0, 0, 0))]



@tdir
def test_file_writer():
    writer = fw.FileWriter(
        file_format=ff.AudioFileFormat(
            channels=1,
            samplerate=48_000,
            format=ff.Format.FLAC,
            subtype=ff.Subtype.PCM_24
        ),
        name='test',
        path=Path('.'),
        silence=SilenceStrategy[int](
            at_start=30,
            at_end=40,
            before_stopping=50,
        ),
    )

    blocks = (17 * O) + (4 * I) + (40 * O) + I + (51 * O) + (20 * I)

    with writer:
        for i, b in enumerate(blocks):
            writer.write(b)
            print(i, sorted(Path('.').iterdir()))

    files = sorted(Path('.').iterdir())
    assert len(files) == 3
