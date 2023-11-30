import click
import dtyper

from recs.base import pyproject, times

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


class ClickTime(click.ParamType):
    name = 'TIME'

    def convert(self, value, param, ctx) -> float:
        if isinstance(value, (int, float)):
            return value
        try:
            return times.to_time(value)
        except ValueError as e:
            self.fail(f'{value!r} is not a valid time: {e.args[0]}', param, ctx)
