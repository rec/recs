import json
import os
import sys
import threading
import typing as t

from recs.cfg import Cfg

from . import dear_gui
from .gui_process import Rows


class StdinRows:
    def __init__(self) -> None:
        self.latest: Rows = []
        self.closed = False
        self.lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._read, daemon=True, name='GuiRows').start()

    def rows(self) -> t.Iterator[t.Mapping[str, object]]:
        with self.lock:
            rows = list(self.latest)
        return iter(rows)

    def _read(self) -> None:
        for line in sys.stdin:
            rows = t.cast(Rows, json.loads(line))
            with self.lock:
                self.latest = rows
        self.closed = True


def main() -> None:
    provider = StdinRows()
    provider.start()
    cfg = Cfg(
        gui=True,
        ui_refresh_rate=float(os.environ.get('RECS_GUI_REFRESH_RATE', '23')),
    )
    dear_gui.Gui(provider.rows, cfg, stop_when=lambda: provider.closed).run()


if __name__ == '__main__':
    main()
