import json

import soundfile as sf

from recs.base.types import Format, SdType
from recs.cfg import device
from recs.ui.recorder import Recorder

from . import Cfg


def run_cli(cfg: Cfg) -> None:
    if cfg.info:
        _info()
    elif cfg.list_types:
        _list_types()
    else:
        Recorder(cfg).run()


def _list_types() -> None:
    avail = sf.available_formats()
    fmts = [f.upper() for f in Format]
    formats = {f: [avail[f], sf.available_subtypes(f)] for f in fmts}
    sdtypes = [str(s) for s in SdType]
    d = {'formats': formats, 'sdtypes': sdtypes}

    print(json.dumps(d, indent=4))


def _info() -> None:
    info = device.query_devices()
    info2 = [i for i in info if i['max_input_channels']]
    print(json.dumps(info2, indent=4))
