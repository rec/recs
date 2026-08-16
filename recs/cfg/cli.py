from typing import Annotated, cast

import tyro

from recs.base import pyproject

from .cfg import Cfg

INTRO = f"""  {pyproject.message()}
============================================="""
LINES = (
    INTRO,
    'Why should there be a record button at all?',
    'I wanted to digitize a huge number of cassettes and LPs, so I wanted a '
    + 'program that ran in the background and recorded everything except quiet.',
    'Nothing like that existed so I wrote it.  Free, open-source, configurable.',
    'Full documentation here: https://github.com/rec/recs',
)
HELP = '\n\n'.join(LINES)

CliCfg = cast(type[Cfg], Annotated[Cfg, tyro.conf.OmitArgPrefixes])
