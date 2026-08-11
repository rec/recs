import os
import subprocess as sp
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping

from pydantic import BaseModel, Field, ValidationError
from threa import Runnable

from recs.base import app_command
from recs.cfg.cfg import Cfg

from .key_events import KeyEvent

Rows = list[dict[str, object]]


class GuiPayload(BaseModel):
    rows: Rows = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class GuiProcess(Runnable):
    def __init__(
        self,
        rows: Callable[[], Iterator[Mapping[str, object]]],
        cfg: Cfg,
        *,
        errors: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        self.rows = rows
        self.errors = errors or tuple
        self.cfg = cfg
        self.enabled = not cfg.console.silent
        self.process: sp.Popen[str] | None = None
        self.key_events: list[KeyEvent] = []
        self.lock = threading.Lock()
        super().__init__()

    def update(self) -> None:
        if not self.enabled or self.process is None or self.process.stdin is None:
            return
        if self.closed:
            return
        if self.process.stdin.closed:
            return

        try:
            payload = GuiPayload(
                rows=[dict(row) for row in self.rows()],
                errors=list(self.errors()),
            )
            self.process.stdin.write(payload.model_dump_json())
            self.process.stdin.write('\n')
            self.process.stdin.flush()
        except ValueError:
            if self.process.stdin.closed:
                return
            raise
        except BrokenPipeError:
            self.process.stdin.close()

    def start(self) -> None:
        if not self.enabled:
            super().start()
            return

        env = os.environ | {
            'RECS_GUI_REFRESH_RATE': str(self.cfg.console.ui_refresh_rate)
        }
        self.process = sp.Popen(
            app_command.command('gui-child'),
            stdin=sp.PIPE,
            stdout=sp.PIPE,
            stderr=sp.DEVNULL,
            text=True,
            env=env,
        )
        threading.Thread(
            target=self._read_key_events,
            daemon=True,
            name='GuiKeyEvents',
        ).start()
        self.update()
        super().start()

    def stop(self) -> None:
        if self.process is not None and self.process.stdin is not None:
            self.process.stdin.close()
        super().stop()

    @property
    def closed(self) -> bool:
        return bool(
            self.enabled
            and self.process is not None
            and self.process.poll() is not None
        )

    def join(self, timeout: float | None = None) -> None:
        if self.process is None:
            return
        try:
            self.process.wait(timeout)
        except sp.TimeoutExpired:
            self.process.terminate()
            self.process.wait()

    def take_key_events(self) -> list[KeyEvent]:
        with self.lock:
            events, self.key_events = self.key_events, []
        return events

    def take_control_requests(self) -> list[object]:
        return []

    def _read_key_events(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        for line in self.process.stdout:
            try:
                event = KeyEvent.model_validate_json(line)
            except ValidationError:
                continue
            with self.lock:
                self.key_events.append(event)
