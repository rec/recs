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
    from recs.audio import monitor
    from recs.ui import audio_display

    top = audio_display.DevicesCallback()
    monitor.Monitor(top.callback, top.table).run()


def run():
    try:
        app(standalone_mode=False)
    except click.ClickException as e:
        return f'{e.__class__.__name__}: {e.message}'
    except click.Abort:
        return 'Aborted'
