from .file_types import DType, Subtype

SUBTYPE_TO_DTYPE = {
    Subtype.alac_16: DType.int16,
    Subtype.alac_20: DType.int32,
    Subtype.alac_24: DType.int32,
    Subtype.alac_32: DType.int32,
    Subtype.double: DType.float32,
    Subtype.dpcm_16: DType.int16,
    Subtype.dpcm_8: DType.int16,
    Subtype.dwvw_12: DType.int16,
    Subtype.dwvw_16: DType.int16,
    Subtype.dwvw_24: DType.int32,
    Subtype.float: DType.float32,
    Subtype.ms_adpcm: DType.int32,
    Subtype.nms_adpcm_16: DType.int16,
    Subtype.nms_adpcm_24: DType.int32,
    Subtype.nms_adpcm_32: DType.int32,
    Subtype.pcm_16: DType.int16,
    Subtype.pcm_24: DType.int32,
    Subtype.pcm_32: DType.int32,
    Subtype.pcm_s8: DType.int16,
    Subtype.pcm_u8: DType.int16,
}

DTYPE_TO_SUBTYPE = {
    DType.int16: Subtype.pcm_16,
    DType.int32: Subtype.pcm_32,
    DType.float32: Subtype.float,
    DType.float64: Subtype.double,
}
