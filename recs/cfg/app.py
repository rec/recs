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

    def convert(self, value, p, ctx) -> float:
        if isinstance(value, (int, float)):
            return value
        try:
            return times.to_time(value)
        except ValueError as e:
            self.fail(f'{p.opts[0]}: {e.args[0]}', p, ctx)


class DictParam(click.ParamType):
    name = 'NONE'
    prefix_dict: dict

    def convert(self, value, p, ctx):
        if not value:
            return None
        if not isinstance(value, str):
            return value
        try:
            return self.prefix_dict[value]
        except KeyError:
            self.fail(f'Cannot understand {p.opts[0]}="{value}"')


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

    def convert(self, value, p, ctx):
        try:
            metadata.to_dict([value])
            return value
        except RecsError as e:
            self.fail(f'In {p.opts[0]}: "{e.args[0]}"')


class AliasParam(click.ParamType):
    name = 'ALIAS'

    def convert(self, value, p, ctx):
        return value
