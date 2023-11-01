from recs.misc.file_list import FileList
from pathlib import Path

import tdir


@tdir
def test_file_list():
    fl = FileList()

    # We will write 8 * i bytes in each file
    ts = 0
    for i in range(8):
        fl.append(Path(str(i)))

        with fl[-1].open('w') as fp:
            for j in range(i):
                fp.write(8 * 'x')
                fp.flush()
                ts += 8
                assert fl.total_size == ts

    assert fl.total_size == 224
