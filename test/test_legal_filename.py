import tdir

from recs.audio.legal_filename import legal_filename


@tdir
def test_legal_filename():
    name = ''.join(chr(i) for i in range(2, 0x150, 7))
    with open(legal_filename(name), 'w') as fp:
        fp.write('ok')
