import json

import sounddevice as sd
import soundfile as sf

from recs.base.types import Format, SdType
from recs.ui.recorder import Recorder

from . import Cfg


def run(cfg: Cfg) -> None:
    if cfg.info:
        info = sd.query_devices(kind=None)
        info = [i for i in info if i['max_input_channels']]
        print(json.dumps(info, indent=4))

    elif cfg.list_types:
        avail = sf.available_formats()
        fmts = [f.upper() for f in Format]
        formats = {f: [avail[f], sf.available_subtypes(f)] for f in fmts}
        sdtypes = [str(s) for s in SdType]
        d = {'formats': formats, 'sdtypes': sdtypes}

        print(json.dumps(d, indent=4))

    else:
        Recorder(cfg).run()
