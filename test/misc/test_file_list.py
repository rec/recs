from pathlib import Path

import tdir

from recs.misc import file_list
from recs.misc.file_list import FileList


@tdir
def test_file_list():
    fl = FileList()

    # We will write 8 * i bytes in each file
    ts = 0
    for i in range(8):
        fl.append(Path(str(i)))

        with fl[-1].open('w') as fp:
            for _ in range(i):
                fp.write(8 * 'x')
                fp.flush()
                ts += 8
                assert fl.total_size == ts

    assert fl.total_size == 224


@tdir
def test_file_list_cached_total_size(monkeypatch):
    times = iter([0.0, 0.5, 1.0])
    monkeypatch.setattr(file_list.time, 'monotonic', lambda: next(times))
    fl = FileList()
    fl.append(Path('active.wav'))
    fl[-1].write_bytes(b'1234')

    assert fl.cached_total_size == 4
    fl[-1].write_bytes(b'12345678')
    assert fl.cached_total_size == 4
    assert fl.cached_total_size == 8
    assert fl.total_size == 8
