from typing import Annotated, cast

import tyro

from recs.base import pyproject
from recs.cfg.cfg import Cfg

INTRO = f"""  {pyproject.message()}
============================================="""
LINES = (
    INTRO,
    'Why should there be a record button at all?',
    'I wanted to digitize a huge number of cassettes and LPs, so I wanted a '
    + 'program that ran in the background and recorded everything except quiet.',
    'Nothing like that existed so I wrote it.  Free, open-source, configurable.',
    'Full documentation here: https://github.com/rec/recs',
    'With no subcommand, recs starts recording. '
    'sessions ROOT lists recordings; session COMMAND manages one recording; '
    'record check PATH validates a recording document and its media.',
    'control pause/resume affect capture; control stop/continue affect playback. '
    'profile manages named saved setups; --profiles loads per-device JSON defaults.',
    'readiness inspects a setup without recording; preflight checks a running daemon.',
)
HELP = '\n\n'.join(LINES)

CliCfg = cast(type[Cfg], Annotated[Cfg, tyro.conf.OmitArgPrefixes])
