import soundfile

from recs.base.types import Format, Subtype

BAD_FORMATS = 'HTK', 'SDS', 'SVX', 'WVE', 'XI'

REMOVED_FORMAT = [
    'aiff',
    'au',
    'avr',
    'caf',
    'ircam',
    'mat4',
    'mat5',
    'mpc2k',
    'nist',
    'paf',
    'pvf',
    'sd2',
    'voc',
    'w64',
    'wavex',
]
REMOVED_SUBTYPE = [
    'alaw',
    'dpcm_16',
    'dpcm_8',
    'dwvw_12',
    'dwvw_16',
    'dwvw_24',
    'dwvw_n',
    'g721_32',
    'g723_24',
    'g723_40',
    'gsm610',
    'ima_adpcm',
    'ms_adpcm',
    'nms_adpcm_16',
    'nms_adpcm_24',
    'nms_adpcm_32',
    'ulaw',
    'vox_adpcm',
]


def test_format():
    expected = sorted(k.lower() for k in soundfile._formats if k not in BAD_FORMATS)
    actual = [k.lower() for k in Format if k]
    assert expected == sorted(actual + REMOVED_FORMAT)


def test_subtype():
    expected = sorted(k.lower() for k in soundfile._subtypes)
    actual = [k.lower() for k in Subtype if k]
    assert expected == sorted(actual + REMOVED_SUBTYPE)
