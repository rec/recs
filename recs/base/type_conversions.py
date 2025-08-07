from .prefix_dict import PrefixDict
from .types import Format, SdType, Subtype

FORMATS = PrefixDict[Format]({str(s): s for s in Format})
SDTYPES = PrefixDict[SdType]({str(s): s for s in SdType})
SUBTYPES = PrefixDict[Subtype]({str(s): s for s in Subtype})

SUBTYPE_TO_SDTYPE = {
    Subtype.alac_16: SdType.int16,
    Subtype.alac_20: SdType.int32,
    Subtype.alac_24: SdType.int32,
    Subtype.alac_32: SdType.int32,
    Subtype.double: SdType.float32,
    Subtype.float: SdType.float32,
    Subtype.pcm_16: SdType.int16,
    Subtype.pcm_24: SdType.int32,
    Subtype.pcm_32: SdType.int32,
    Subtype.pcm_s8: SdType.int16,
    Subtype.pcm_u8: SdType.int16,
}

SDTYPE_TO_SUBTYPE = {
    SdType.int16: Subtype.pcm_16,
    SdType.int32: Subtype.pcm_32,
    SdType.float32: Subtype.float,
}
