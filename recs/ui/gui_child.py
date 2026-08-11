import os
import sys
import threading
from collections.abc import Iterator, Mapping

from pydantic import TypeAdapter, ValidationError

from recs.cfg.cfg import Cfg

from .gui_process import GuiPayload, Rows
from .key_events import KeyEvent
from .pyside_gui import Gui

ROWS = TypeAdapter(Rows)
PAYLOAD = TypeAdapter(GuiPayload)


class StdinRows:
    def __init__(self) -> None:
        self.latest = GuiPayload()
        self.closed = False
        self.lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._read, daemon=True, name='GuiRows').start()

    def rows(self) -> Iterator[Mapping[str, object]]:
        with self.lock:
            rows = list(self.latest.rows)
        return iter(rows)

    def errors(self) -> list[str]:
        with self.lock:
            return list(self.latest.errors)

    def _read(self) -> None:
        for line in sys.stdin:
            try:
                payload = PAYLOAD.validate_json(line)
            except ValidationError:
                try:
                    payload = GuiPayload(rows=ROWS.validate_json(line))
                except ValidationError:
                    continue
            with self.lock:
                self.latest = payload
        self.closed = True


def main() -> None:
    provider = StdinRows()
    provider.start()
    cfg = Cfg(
        gui=True,
        ui_refresh_rate=float(os.environ.get('RECS_GUI_REFRESH_RATE', '23')),
    )
    Gui(
        provider.rows,
        cfg,
        errors=provider.errors,
        stop_when=lambda: provider.closed,
        record_key=_write_key_event,
    ).run()


def _write_key_event(event: KeyEvent) -> None:
    print(event.model_dump_json(), flush=True)


if __name__ == '__main__':
    main()
