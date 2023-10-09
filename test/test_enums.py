import soundfile as sf

from recs.audio.file_types import Format, Subtype

BAD_FORMATS = 'HTK', 'SDS', 'SVX', 'WVE', 'XI'


def test_format():
    expected = sorted(k.lower() for k in sf._formats if k not in BAD_FORMATS)
    actual = [k.lower() for k in Format if k]
    assert expected == actual


def test_subtype():
    expected = sorted(k.lower() for k in sf._subtypes)
    actual = [k.lower() for k in Subtype if k]
    assert expected == actual
