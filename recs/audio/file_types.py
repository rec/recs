from enum import StrEnum, auto

import sounddevice as sd


class DType(StrEnum):
    none = ''

    int16 = auto()
    int32 = auto()
    float32 = auto()
    float64 = auto()


DTYPE = DType[sd.default.dtype[0]]


class Format(StrEnum):
    none = ''

    AIFF = auto()
    AU = auto()
    AVR = auto()
    CAF = auto()
    FLAC = auto()
    IRCAM = auto()
    MAT4 = auto()
    MAT5 = auto()
    MP3 = auto()
    MPC2K = auto()
    NIST = auto()
    OGG = auto()
    PAF = auto()
    PVF = auto()
    RAW = auto()
    RF64 = auto()
    SD2 = auto()
    VOC = auto()
    W64 = auto()
    WAV = auto()
    WAVEX = auto()


class Subtype(StrEnum):
    none = ''

    ALAC_16 = auto()
    ALAC_20 = auto()
    ALAC_24 = auto()
    ALAC_32 = auto()
    ALAW = auto()
    DOUBLE = auto()
    DPCM_16 = auto()
    DPCM_8 = auto()
    DWVW_12 = auto()
    DWVW_16 = auto()
    DWVW_24 = auto()
    DWVW_N = auto()
    FLOAT = auto()
    G721_32 = auto()
    G723_24 = auto()
    G723_40 = auto()
    GSM610 = auto()
    IMA_ADPCM = auto()
    MPEG_LAYER_I = auto()
    MPEG_LAYER_II = auto()
    MPEG_LAYER_III = auto()
    MS_ADPCM = auto()
    NMS_ADPCM_16 = auto()
    NMS_ADPCM_24 = auto()
    NMS_ADPCM_32 = auto()
    OPUS = auto()
    PCM_16 = auto()
    PCM_24 = auto()
    PCM_32 = auto()
    PCM_S8 = auto()
    PCM_U8 = auto()
    ULAW = auto()
    VORBIS = auto()
    VOX_ADPCM = auto()
