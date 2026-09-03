from typing import TypeVar

from reccy import config, units
from tyro.constructors import PrimitiveConstructorSpec

from recs.base import types
from recs.base.prefix_dict import PrefixDict
from recs.base.type_conversions import FORMATS, SDTYPES, SUBTYPES

_T = TypeVar('_T')


def _prefix_spec(
    values: PrefixDict[_T], metavar: str, *, trim_dots: bool = False
) -> PrimitiveConstructorSpec[_T]:
    def parse(args: list[str]) -> _T:
        value = args[0].strip()
        if trim_dots:
            value = value.strip('.')
        try:
            return values[value]
        except KeyError:
            raise ValueError(f'Cannot understand {metavar}="{args[0]}"') from None

    return PrimitiveConstructorSpec(
        nargs=1,
        metavar=metavar,
        instance_from_str=parse,
        is_instance=lambda value: value in values.values(),
        str_from_instance=lambda value: [str(value)],
    )


FORMAT_SPEC = _prefix_spec(FORMATS, 'AUDIO FORMAT', trim_dots=True)
RECORD_KEYS = PrefixDict({value: value for value in types.RecordKeys})
RECORD_KEYS_SPEC = _prefix_spec(RECORD_KEYS, 'KEY RECORDING MODE')
SDTYPE_SPEC = _prefix_spec(SDTYPES, 'NUMERIC TYPE', trim_dots=True)
SUBTYPE_SPEC = _prefix_spec(SUBTYPES, 'AUDIO SUBTYPE', trim_dots=True)
TIME_SPEC = config.unit_spec(units.Seconds, 'TIME')
MILLISECONDS_SPEC = config.unit_spec(units.WholeMilliseconds, 'MILLISECONDS')
HERTZ_SPEC = config.unit_spec(units.Hertz, 'HZ')
BYTES_SPEC = config.unit_spec(units.Bytes, 'BYTES')
MEGABYTES_SPEC = config.unit_spec(units.Megabytes, 'MB')
