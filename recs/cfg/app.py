import typing as t

import click
import dtyper

from recs.base import RecsError, pyproject, times
from recs.base.type_conversions import FORMATS, SDTYPES, SUBTYPES

from . import metadata

INTRO = f"""
  {pyproject.message()}

============================================="""
LINES = (
    INTRO,
    'Why should there be a record button at all?',
    'I wanted to digitize a huge number of cassettes and LPs, so I wanted a '
    + 'program that ran in the background and recorded everything except quiet.',
    'Nothing like that existed so I wrote it.  Free, open-source, configurable.',
    'Full documentation here: https://github.com/rec/recs',
    '',
)
HELP = '\n\n\n\n'.join(LINES)

app = dtyper.Typer(
    add_completion=False,
    context_settings={'help_option_names': ['--help', '-h']},
)


class TimeParam(click.ParamType):
    name = 'TIME'

    def convert(
        self,
        value: t.Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> float:
        if isinstance(value, (int, float)):
            return value
        try:
            return times.to_time(value)
        except ValueError as e:
            option = param.opts[0] if param else self.name
            self.fail(f'{option}: {e.args[0]}', param, ctx)


class DictParam(click.ParamType):
    name = 'NONE'
    prefix_dict: dict[str, t.Any]

    def convert(
        self,
        value: t.Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> t.Any:
        if not value:
            return None
        if not isinstance(value, str):
            return value
        try:
            return self.prefix_dict[value]
        except KeyError:
            option = param.opts[0] if param else self.name
            self.fail(f'Cannot understand {option}="{value}"', param, ctx)


class FormatParam(DictParam):
    name = 'AUDIO FORMAT'
    prefix_dict = FORMATS


class SdTypeParam(DictParam):
    name = 'NUMERIC TYPE'
    prefix_dict = SDTYPES


class SubtypeParam(DictParam):
    name = 'AUDIO SUBTYPE'
    prefix_dict = SUBTYPES


class MetadataParam(click.ParamType):
    name = 'METADATA'

    def convert(
        self,
        value: t.Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> t.Any:
        try:
            metadata.to_dict([value])
            return value
        except RecsError as e:
            option = param.opts[0] if param else self.name
            self.fail(f'In {option}: "{e.args[0]}"', param, ctx)


class AliasParam(click.ParamType):
    name = 'ALIAS'

    def convert(
        self,
        value: t.Any,
        param: click.Parameter | None,
        ctx: click.Context | None,
    ) -> t.Any:
        return value
