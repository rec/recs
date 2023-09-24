import json
import typing as t

import dtyper
import sounddevice as sd

from recs.__main__ import recs
from recs.ui import audio_display

from . import monitor


def run(d):
    return Recs(**d)()


@dtyper.dataclass(recs)
class Recs:
    def __call__(self):
        if self.info:
            _info()
        else:
            top = audio_display.DevicesCallback()
            monitor.Monitor(top.callback, top.table).run()


def _info(kind: t.Optional[str] = None):
    info = sd.query_devices(kind=kind)

    def accept(k):
        if 'channel' in k:
            return k.replace('max_', '')
        if 'sample' in k:
            return 'sample_rate'

    def to_entry(d):
        return d['name'], {j: v for k, v in d.items() if (j := accept(k))}

    info = dict(to_entry(d) for d in info)

    print(json.dumps(info, indent=2))
