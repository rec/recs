from typer import Typer
import click
import sys

ICON = '🎙'
CLI_NAME = 'recs'

app = Typer(
    add_completion=False,
    context_settings={'help_option_names': ['--help', '-h']},
    help=f"""\
{ICON} {CLI_NAME} {ICON}

Usage: {CLI_NAME} [GLOBAL-FLAGS] [COMMAND] [COMMAND-FLAGS] [COMMAND-ARGS]
""")

command = app.command


@command(help='Record')
def rec():
    pass


@command(help='Check levels')
def check():
    pass


@command(help='Info')
def info():
    import sounddevice as sd
    import json

    info = sd.query_devices()
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
