from pathlib import Path

import tdir

from recs.misc import legal_filename


@tdir
def test_legal_filename():
    name = ''.join(chr(i) for i in range(2, 0x150, 7))
    with open(legal_filename.legal_filename(name), 'w') as fp:
        fp.write('ok')


def test_legal_filename_replaces_problematic_characters() -> None:
    assert legal_filename.legal_filename(r'\/:*?"<>|') == '---------'
    assert legal_filename.legal_filename('.,;= ') == '.,;= '


def test_legal_path_replaces_each_filename_segment() -> None:
    assert legal_filename.legal_path(Path('/tmp/device:name/track?')) == Path(
        '/tmp/device-name/track-'
    )
