from recs.audio.file_types import Format, Subtype


def is_valid(format: Format, subtype: Subtype) -> bool:
    return subtype in VALID_SUBTYPES.get(format, ())


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
