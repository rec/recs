import json

import soundfile

from recs.base import RecsError
from recs.base.types import Format, SdType
from recs.cfg import device
from recs.daemon import gui_ipc
from recs.daemon.root_user import raise_if_root
from recs.ui.recorder import Recorder

from . import Cfg


def run_cli(cfg: Cfg) -> None:
    if gui_ipc.daemon_mode_enabled():
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
        Recorder(cfg).run()


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
