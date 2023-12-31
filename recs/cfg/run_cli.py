import json

import soundfile as sf

from recs.base.types import Format, SdType
from recs.cfg import device
from recs.ui.recorder import Recorder

from . import Cfg


def run_cli(cfg: Cfg) -> None:
    if cfg.info:
        return _info()

    if cfg.list_types:
        return _list_types()

    rec = Recorder(cfg)
    try:
        rec.run_recorder()
    finally:
        if cfg.calibrate:
            states = rec.state.state.items()
            d = {j: {k: v.db_range for k, v in u.items()} for j, u in states}
            d2 = {'(all)': rec.state.total.db_range}
            print(json.dumps(d | d2, indent=2))


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
