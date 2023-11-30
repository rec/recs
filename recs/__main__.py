import sys

import click

from recs.base import RecsError
from recs.cfg import app, cli

assert cli


def run() -> int:
    try:
        app.app(prog_name='recs', standalone_mode=False)
        return 0

    except RecsError as e:
        print('ERROR:', *e.args, file=sys.stderr)

    except click.ClickException as e:
        print(f'{e.__class__.__name__}: {e.message}', file=sys.stderr)

    except click.Abort:
        print('Interrupted', file=sys.stderr)

    return -1


if __name__ == '__main__':
    sys.exit(run())
