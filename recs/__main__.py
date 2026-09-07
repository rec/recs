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
        if len(sys.argv) > 1 and sys.argv[1] == 'preflight':
            from recs.daemon.preflight import main

            return main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'control':
            from recs.daemon.control_cli import main

            return main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'watch':
            from recs.daemon.watch import main

            return main(sys.argv[2:])
        if len(sys.argv) > 1 and sys.argv[1] == 'profile':
            from recs.cfg import setup_profiles

            return setup_profiles.main(sys.argv[2:])
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
            if len(sys.argv) > 2 and sys.argv[2] == 'migrate':
                from recs.recording.migrate import main

                return main(sys.argv[3:])
            if len(sys.argv) > 2 and sys.argv[2] == 'export':
                from recs.ui import session_export

                return session_export.main(sys.argv[3:])
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
        from recs.cfg import setup_profiles

        profile, arguments = setup_profiles.profile_argument(sys.argv[1:])
        if profile is None:
            cfg = tyro.cli(
                cli.CliCfg, args=arguments, prog='recs', description=cli.HELP
            )
            run_cli.run_cli(cfg)
        else:
            loaded = setup_profiles.configured(profile, arguments)
            run_cli.run_cli(loaded.cfg, loaded)
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
