import multiprocessing as mp
import sys

import tyro
from pydantic import ValidationError
from reccy.runtime import logging

from recs.base._query_device import devices_json, stream_devices
from recs.base.errors import RecsError
from recs.cfg import cli, run_cli

LOGGER = logging.get_logger(__name__)


def run() -> int:
    mp.freeze_support()
    logging.configure()
    try:
        if len(sys.argv) > 1 and sys.argv[1] == 'daemon':
            from recs.daemon.cli import main

            return main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'gui-child':
            from recs.ui.gui_child import main

            main()
            return 0
        if len(sys.argv) > 1 and sys.argv[1] == 'query-devices':
            print(devices_json())
            return 0
        if len(sys.argv) > 1 and sys.argv[1] == 'query-devices-stream':
            stream_devices()
            return 0
        if len(sys.argv) > 1 and sys.argv[1] == 'sessions':
            from recs.ui import session_browser

            return session_browser.main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'session':
            from recs.ui import session_browser

            return session_browser.main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'test-input':
            from recs.ui import input_self_test

            return input_self_test.main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'explain':
            from recs.ui import session_explain

            return session_explain.main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'record':
            from recs.ui import session_record_check

            return session_record_check.main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'edit':
            from recs.edit.cli import main

            return main(sys.argv[2:])
        cfg = tyro.cli(cli.CliCfg, prog='recs', description=cli.HELP)
        run_cli.run_cli(cfg)
        return 0

    except KeyboardInterrupt:
        LOGGER.warning('Interrupted')
        return 0

    except ValidationError as e:
        LOGGER.error('%s', e)

    except RecsError as e:
        LOGGER.error('%s', e)

    return -1


if __name__ == '__main__':
    sys.exit(run())
