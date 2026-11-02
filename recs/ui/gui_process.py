import os
import subprocess as sp
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping

from pydantic import BaseModel, Field, ValidationError
from reccy.runtime import logging
from reccy.runtime.process import terminate
from reccy.runtime.publication import LatestPublisher
from threa import Runnable

from recs.base import app_command
from recs.cfg.cfg import Cfg

from .key_events import KeyEvent

Rows = list[dict[str, object]]


LOGGER = logging.get_logger(__name__)


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
        self.publisher: LatestPublisher[GuiPayload] | None = None
        super().__init__()

    def update(self) -> None:
        if not self.enabled or self.process is None or self.process.stdin is None:
            return
        if self.closed:
            return
        if self.publisher is not None:
            self.publisher.publish(
                GuiPayload(
                    rows=[dict(r) for r in self.rows()], errors=list(self.errors())
                )
            )

    def _write(self, payload: GuiPayload) -> None:
        assert self.process is not None and self.process.stdin is not None
        try:
            self.process.stdin.write(payload.model_dump_json() + '\n')
            self.process.stdin.flush()
        except BrokenPipeError:
            return
        except ValueError:
            if not self.process.stdin.closed:
                raise

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
        self.publisher = LatestPublisher(self._write, name='GuiSnapshots')
        self.update()
        super().start()

    def stop(self) -> None:
        # Never close a buffered pipe while its writer may hold the stream lock.
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
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
        deadline = 1.0 if timeout is None else max(0.0, timeout)
        try:
            terminate(self.process, timeout=deadline)
        except sp.TimeoutExpired:
            LOGGER.error('GUI process did not exit after terminate and kill')
        if self.publisher is not None and self.publisher.close(deadline):
            if self.process.stdin is not None:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass

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
                if len(self.key_events) < 1024:
                    self.key_events.append(event)
