from enum import StrEnum, auto


class Format(StrEnum):
    AIFF = auto()
    AU = auto()
    AVR = auto()
    CAF = auto()
    FLAC = auto()
    HTK = auto()
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
    SDS = auto()
    SVX = auto()
    VOC = auto()
    W64 = auto()
    WAV = auto()
    WAVEX = auto()
    WVE = auto()
    XI = auto()


class Subtype(StrEnum):
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


VALID_SUBTYPES = {
    Format.AIFF: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.PCM_U8,
        Subtype.FLOAT,
        Subtype.DOUBLE,
        Subtype.IMA_ADPCM,
    ],
    Format.AU: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.FLOAT,
        Subtype.DOUBLE,
    ],
    Format.AVR: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_U8,
    ],
    Format.CAF: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.FLOAT,
        Subtype.DOUBLE,
        Subtype.ALAC_16,
        Subtype.ALAC_20,
        Subtype.ALAC_24,
        Subtype.ALAC_32,
    ],
    Format.FLAC: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
    ],
    Format.IRCAM: [
        Subtype.PCM_16,
        Subtype.PCM_32,
        Subtype.FLOAT,
    ],
    Format.MAT4: [
        Subtype.PCM_16,
        Subtype.PCM_32,
        Subtype.FLOAT,
        Subtype.DOUBLE,
    ],
    Format.MAT5: [
        Subtype.PCM_16,
        Subtype.PCM_32,
        Subtype.PCM_U8,
        Subtype.FLOAT,
        Subtype.DOUBLE,
    ],
    Format.MPC2K: [
        Subtype.PCM_16,
    ],
    Format.NIST: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
    ],
    Format.OGG: [
        Subtype.VORBIS,
        Subtype.OPUS,
    ],
    Format.PAF: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
    ],
    Format.PVF: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_32,
    ],
    Format.RAW: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.PCM_U8,
        Subtype.FLOAT,
        Subtype.DOUBLE,
    ],
    Format.RF64: [
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.PCM_U8,
        Subtype.FLOAT,
        Subtype.DOUBLE,
    ],
    Format.SD2: [
        Subtype.PCM_S8,
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
    ],
    Format.VOC: [
        Subtype.PCM_16,
        Subtype.PCM_U8,
    ],
    Format.W64: [
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.PCM_U8,
        Subtype.FLOAT,
        Subtype.DOUBLE,
        Subtype.IMA_ADPCM,
        Subtype.MS_ADPCM,
    ],
    Format.WAV: [
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.PCM_U8,
        Subtype.FLOAT,
        Subtype.DOUBLE,
        Subtype.IMA_ADPCM,
        Subtype.MS_ADPCM,
    ],
    Format.WAVEX: [
        Subtype.PCM_16,
        Subtype.PCM_24,
        Subtype.PCM_32,
        Subtype.PCM_U8,
        Subtype.FLOAT,
        Subtype.DOUBLE,
    ],
}
