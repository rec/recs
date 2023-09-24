import dtyper

from recs.__main__ import recs
from recs.ui import audio_display

from . import info, monitor


@dtyper.dataclass(recs)
class Recs:
    def __call__(self):
        if self.info:
            info.info()
        else:
            top = audio_display.DevicesCallback()
            monitor.Monitor(top.callback, top.table).run()


def run(d):
    return Recs(**d)()
