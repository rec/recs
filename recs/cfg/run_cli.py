import json
import sys
import time

import soundfile
from reccy.configuration.settings import write_json_model

from recs.base.errors import ErrorRecord, RecsError
from recs.base.types import Format, SdType
from recs.cfg import device
from recs.daemon import gui_ipc, paths
from recs.daemon.models import DaemonStatus
from recs.daemon.root_user import raise_if_root
from recs.ui.recorder import Recorder

from . import settings
from .cfg import FLAT_FIELDS, Cfg


def run_cli(cfg: Cfg) -> None:
    daemon_mode = gui_ipc.daemon_mode_enabled()
    try:
        if daemon_mode:
            raise_if_root()
        if cfg.general.info:
            _info()
        elif cfg.general.list_types:
            _list_types()
        elif cfg.console.remote:
            metadata = gui_ipc.load_metadata()
            if metadata is None or not gui_ipc.endpoint_reachable(metadata):
                raise RecsError('recs daemon is not running')
            gui_ipc.run_remote_gui(metadata, cfg)
        else:
            loaded = settings.load(cfg, _cli_overrides())
            if loaded.cfg.save_settings:
                Recorder(loaded.cfg, loaded).run()
            else:
                Recorder(loaded.cfg).run()
    except Exception as e:
        if daemon_mode:
            _write_failed_status(e)
        raise


def _write_failed_status(error: Exception) -> None:
    status = DaemonStatus(
        errors=[
            ErrorRecord(
                timestamp='',
                message=f'{type(error).__name__}: {error}',
            )
        ],
        recording=False,
        updated_at=time.time(),
    )
    try:
        write_json_model(
            paths.service_paths(paths.current_platform()).status, status, sync=True
        )
    except OSError:
        return


def _list_types() -> None:
    avail = soundfile.available_formats()
    fmts = [f.upper() for f in Format]
    formats = {f: [avail[f], soundfile.available_subtypes(f)] for f in fmts}
    sdtypes = [str(s) for s in SdType]
    d = {'formats': formats, 'sdtypes': sdtypes}

    print(json.dumps(d, indent=4))


def _info() -> None:
    info = device.query_devices()
    info2 = [i for i in info if i['max_input_channels']]
    print(json.dumps(info2, indent=4))


def _cli_overrides() -> set[str]:
    options = {
        '-B': 'band_mode',
        '-b': 'quiet_before_start',
        '-c': 'quiet_after_end',
        '-m': 'metadata',
        '-o': 'output_directory',
        '-R': 'record_everything',
        '-t': 'total_run_time',
        '-z': 'noise_floor',
    }
    fields: set[str] = set()
    for argument in sys.argv[1:]:
        option = argument.split('=', 1)[0]
        if option in options:
            fields.add(options[option])
        elif option.startswith('--'):
            field = option.removeprefix('--no-').removeprefix('--').replace('-', '_')
            if field in FLAT_FIELDS:
                fields.add(field)
    return {f'{FLAT_FIELDS[field]}.{field}' for field in fields}
