import json
import multiprocessing as mp
import sys

import tyro
from pydantic import ValidationError

from recs.base import RecsError
from recs.base._query_device import _query_devices
from recs.cfg import cli
from recs.daemon import cli as daemon_cli


def run() -> int:
    mp.freeze_support()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'daemon':
            return daemon_cli.main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'gui-child':
            from recs.ui.gui_child import main as gui_child

            gui_child()
            return 0
        if len(sys.argv) > 1 and sys.argv[1] == 'query-devices':
            print(json.dumps(_query_devices(), indent=4))
            return 0
        if len(sys.argv) > 1 and sys.argv[1] == 'sessions':
            from recs.ui import session_browser

            return session_browser.main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'test-input':
            from recs.ui import input_self_test

            return input_self_test.main(sys.argv[2:])
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
