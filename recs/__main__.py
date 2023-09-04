import sys
import typing as t

import click
import dtyper as ty

ICON = '🎙'
CLI_NAME = 'recs'

app = ty.Typer(
    add_completion=False,
    context_settings={'help_option_names': ['--help', '-h']},
    help=f"""\
{ICON} {CLI_NAME} {ICON}

Usage: {CLI_NAME} [GLOBAL-FLAGS] [COMMAND] [COMMAND-FLAGS] [COMMAND-ARGS]
""",
)

command = app.command


@command(help='Record')
def rec():
    pass


@command(help='Check levels')
def check():
    from recs import audio_display

    from . import monitor

    top = audio_display.Top()
    monitor.Monitor(top.callback, top.table).run()


@command(help='Info')
def info(
    kind: t.Optional[str] = ty.Argument(None),
):
    import json

    import sounddevice as sd

    info = sd.query_devices(kind=kind)

    def accept(k):
        if 'channel' in k:
            return k.replace('max_', '')
        if 'sample' in k:
            return 'sample_rate'

    def to_entry(d):
        return d['name'], {j: v for k, v in d.items() if (j := accept(k))}

    info = dict(to_entry(d) for d in info)

    print(json.dumps(info, indent=2))


def run():
    try:
        app(standalone_mode=False)
    except click.ClickException as e:
        return f'{e.__class__.__name__}: {e.message}'
    except click.Abort:
        return 'Aborted'


if __name__ == '__main__':
    sys.exit(run())
