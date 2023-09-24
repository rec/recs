import json

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
            info = sd.query_devices(kind=None)
            print(json.dumps(info, indent=2))
        else:
            top = audio_display.DevicesCallback()
            monitor.Monitor(top.callback, top.table).run()
