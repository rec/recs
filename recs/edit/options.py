from typing import Annotated

import tyro
from pydantic import BaseModel, ConfigDict, Field
from reccy.configuration import units
from reccy.configuration.tyro import unit_spec

from recs.base.types import Format, Subtype
from recs.edit.schema import NormalizeMode

TIME_SPEC = unit_spec(units.Seconds, 'TIME')


class EditOptions(BaseModel, frozen=True):
    channel: Annotated[
        list[str], tyro.conf.arg(help='SOURCE:TRACK selector; repeat to select several')
    ] = Field(default_factory=list)

    start: Annotated[
        units.Seconds,
        TIME_SPEC,
        tyro.conf.arg(help='Start time within the source'),
    ] = 0

    end: Annotated[
        units.Seconds | None,
        TIME_SPEC,
        tyro.conf.arg(help='End time within the source'),
    ] = None

    interval: Annotated[
        list[str],
        tyro.conf.arg(help='START:END source interval; repeat for stitch'),
    ] = Field(default_factory=list)

    format: Format | None = None

    subtype: Subtype | None = None

    normalize: NormalizeMode | None = None

    gain: float | None = None

    route_gain: Annotated[
        list[float], tyro.conf.arg(help='Initial gain for each selected mix route')
    ] = Field(default_factory=list)

    crossfade: Annotated[
        units.Seconds | None,
        TIME_SPEC,
        tyro.conf.arg(help='Crossfade the first two selected mix routes'),
    ] = None

    model_config = ConfigDict(extra='forbid')
