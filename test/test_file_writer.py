import dataclasses as dc
from pathlib import Path

import numpy as np
import soundfile as sf
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

    blocks = (17 * O) + (4 * I) + (40 * O) + I + (51 * O) + (19 * I)

    with writer:
        [writer.write(b) for b in blocks]

    contents, samplerates = zip(*(sf.read(f) for f in sorted(Path('.').iterdir())))

    assert samplerates == (48000, 48000, 48000,)
    lengths = [len(c) for c in contents]
    assert lengths == [56, 44, 104]

    segments = [list(_segments(c)) for c in contents]
    assert segments == [[28, 16, 12], [28, 4, 12], [28, 76]]


def _segments(it):
    pb = False
    pi = 0

    for i, x in enumerate(it):
        if (b := bool(x)) != pb:
            yield i - pi
            pb = b
            pi = i
    yield i + 1 - pi
