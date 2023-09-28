import soundfile as sf

from recs.audio.file_types import Format, Subtype


def test_format():
    expected = sorted(k.lower() for k in sf._formats)
    actual = [k.lower() for k in Format]
    assert expected == actual


def test_subtype():
    expected = sorted(k.lower() for k in sf._subtypes)
    actual = [k.lower() for k in Subtype]
    assert expected == actual
