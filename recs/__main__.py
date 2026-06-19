import sys

import tyro

from recs.base import RecsError
from recs.cfg import cli


def run() -> int:
    try:
        tyro.cli(cli.recs, prog='recs', description=cli.HELP)
        return 0

    except RecsError as e:
        print('ERROR:', *e.args, file=sys.stderr)

    return -1


if __name__ == '__main__':
    sys.exit(run())
