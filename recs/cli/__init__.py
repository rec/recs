import click

from . import info
from .app import app, command

__all__ = 'check', 'info', 'rec', 'run'


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
