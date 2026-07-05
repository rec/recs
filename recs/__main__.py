import sys

import tyro
from pydantic import ValidationError

from recs.base import RecsError
from recs.cfg import cli
from recs.daemon import cli as daemon_cli


def run() -> int:
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'daemon':
            return daemon_cli.main(sys.argv[2:])
        tyro.cli(cli.recs, prog='recs', description=cli.HELP)
        return 0

    except KeyboardInterrupt:
        print('Interrupted', file=sys.stderr)
        return 0

    except ValidationError as e:
        print('ERROR:', e, file=sys.stderr)

    except RecsError as e:
        print('ERROR:', *e.args, file=sys.stderr)

    return -1


if __name__ == '__main__':
    sys.exit(run())
