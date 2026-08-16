from typing import TypeVar

from tyro.constructors import PrimitiveConstructorSpec

from recs.base import times, types
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
TIME_SPEC = PrimitiveConstructorSpec[float](
    nargs=1,
    metavar='TIME',
    instance_from_str=lambda args: times.to_time(args[0]),
    is_instance=lambda value: isinstance(value, (int, float)),
    str_from_instance=lambda value: [str(value)],
)
