import dataclasses as dc
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
import tdir

from recs import array
from recs.audio import block, channel_writer, file_opener, format, subtype
from recs.audio.silence import SilenceStrategy

I, O = [array((1, -1, 1, -1))], [array((0, 0, 0, 0))]

ARRAYS1 = (17 * O) + (4 * I) + (40 * O) + I + (51 * O) + (19 * I)
RESULT1 = [[28, 16, 12], [28, 4, 12], [28, 76]]
ARRAYS2 = (4 * I) + (3 * O) + I + (2000 * O) + (3 * I)
RESULT2 = [[0, 16, 12, 4, 12], [28, 12]]
SAMPLERATE = 48_000


@pytest.mark.parametrize('arrays, segments', [(ARRAYS1, RESULT1), (ARRAYS2, RESULT2)])
@tdir
def test_channel_writer(arrays, segments):
    writer = channel_writer.ChannelWriter(
        opener=file_opener.FileOpener(
            channels=1,
            format=format.Format.flac,
            samplerate=SAMPLERATE,
            subtype=subtype.Subtype.pcm_24
        ),
        name='test',
        path=Path('.'),
        silence=SilenceStrategy[int](
            before_start=30,
            after_end=40,
            stop_after=50,
        ),
    )

    with writer:
        [writer.write(block.Block(a)) for a in arrays]

    contents, samplerates = zip(*(sf.read(f) for f in sorted(Path('.').iterdir())))

    assert all(s == SAMPLERATE for s in samplerates)
    assert segments == [list(_segments(c)) for c in contents]


def _segments(it):
    pb = False
    pi = 0

    for i, x in enumerate(it):
        if (b := bool(x)) != pb:
            yield i - pi
            pb = b
            pi = i
    yield i + 1 - pi
