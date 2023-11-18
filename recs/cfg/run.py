import json
import multiprocessing as mp
import subprocess as sp
import time

import soundfile as sf

from recs.base.types import Format, SdType
from recs.ui.recorder import Recorder

from . import Cfg


def run(cfg: Cfg) -> None:
    if cfg.info:
        _info()

    elif cfg.list_types:
        avail = sf.available_formats()
        fmts = [f.upper() for f in Format]
        formats = {f: [avail[f], sf.available_subtypes(f)] for f in fmts}
        sdtypes = [str(s) for s in SdType]
        d = {'formats': formats, 'sdtypes': sdtypes}

        print(json.dumps(d, indent=4))

    else:
        Recorder(cfg).run()


def _info():
    import sounddevice as sd

    info = sd.query_devices(kind=None)
    info = [i for i in info if i['max_input_channels']]
    print(json.dumps(info, indent=4))


if False:

    def _info2():
        while True:
            _query()
            time.sleep(1)

    def _info3():
        assert mp and sp

        while True:
            sp.run('python -m sounddevice'.split())
            time.sleep(2)

    def _query():
        import sounddevice as sd

        info = sd.query_devices(kind=None)
        print(sorted(i['name'] for i in info if i['max_input_channels']))

    def _info4():
        assert mp and sp
        mp.set_start_method('fork')
        _query()

        while True:
            mp.Process(target=_query).start()
            time.sleep(2)
