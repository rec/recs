import typing as t
from enum import auto

from strenum import StrEnum

DeviceDict = dict[str, float | int | str]
Stop = t.Callable[[], None]


class Active(StrEnum):
    active = auto()
    inactive = auto()
    offline = auto()


class SdType(StrEnum):
    float32 = auto()
    int16 = auto()
    int32 = auto()


SDTYPE = SdType.float32


class Format(StrEnum):
    aiff = auto()
    au = auto()
    avr = auto()
    caf = auto()
    flac = auto()
    ircam = auto()
    mat4 = auto()
    mat5 = auto()
    mp3 = auto()
    mpc2k = auto()
    nist = auto()
    ogg = auto()
    paf = auto()
    pvf = auto()
    raw = auto()
    rf64 = auto()
    sd2 = auto()
    voc = auto()
    w64 = auto()
    wav = auto()
    wavex = auto()


class Subtype(StrEnum):
    alac_16 = auto()
    alac_20 = auto()
    alac_24 = auto()
    alac_32 = auto()
    alaw = auto()
    double = auto()
    dpcm_16 = auto()
    dpcm_8 = auto()
    dwvw_12 = auto()
    dwvw_16 = auto()
    dwvw_24 = auto()
    dwvw_n = auto()
    float = auto()
    g721_32 = auto()
    g723_24 = auto()
    g723_40 = auto()
    gsm610 = auto()
    ima_adpcm = auto()
    mpeg_layer_i = auto()
    mpeg_layer_ii = auto()
    mpeg_layer_iii = auto()
    ms_adpcm = auto()
    nms_adpcm_16 = auto()
    nms_adpcm_24 = auto()
    nms_adpcm_32 = auto()
    opus = auto()
    pcm_16 = auto()
    pcm_24 = auto()
    pcm_32 = auto()
    pcm_s8 = auto()
    pcm_u8 = auto()
    ulaw = auto()
    vorbis = auto()
    vox_adpcm = auto()
