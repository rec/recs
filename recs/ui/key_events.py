import importlib
import select
import sys
import termios
import threading
import tty
import typing as t

from pydantic import BaseModel
from threa import Runnable

from recs.base.types import RecordKeys
from recs.cfg import Cfg


class Listener(t.Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class KeyEvent(BaseModel):
    type: str
    key: str


class NullKeyRecorder(Runnable):
    def take_events(self) -> list[KeyEvent]:
        return []


class TerminalKeyRecorder(Runnable):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[KeyEvent] = []
        self.original_termios: t.Any | None = None

    def start(self) -> None:
        if not sys.stdin.isatty():
            return
        self.original_termios = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin)
        super().start()

    def stop(self) -> None:
        if self.original_termios is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.original_termios)
            self.original_termios = None
        super().stop()

    def update(self) -> None:
        if not self.running:
            return
        readable, _, _ = select.select([sys.stdin], [], [], 0)
        if not readable:
            return
        for char in sys.stdin.read(1):
            self.events.append(KeyEvent(type='key_pressed', key=char))

    def take_events(self) -> list[KeyEvent]:
        self.update()
        events, self.events = self.events, []
        return events


class PynputKeyRecorder(Runnable):
    def __init__(self, record_keys: RecordKeys) -> None:
        super().__init__()
        self.record_keys = record_keys
        self.events: list[KeyEvent] = []
        self.lock = threading.Lock()
        self.listener: Listener | None = None

    def start(self) -> None:
        keyboard = importlib.import_module('pynput.keyboard')
        release = self._on_release if self.record_keys == RecordKeys.all else None
        self.listener = t.cast(
            Listener,
            keyboard.Listener(
                on_press=self._on_press,
                on_release=release,
            ),
        )
        self.listener.start()
        super().start()

    def stop(self) -> None:
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        super().stop()

    def take_events(self) -> list[KeyEvent]:
        with self.lock:
            events, self.events = self.events, []
        return events

    def _on_press(self, key: object) -> None:
        self._append(KeyEvent(type='key_pressed', key=_pynput_key_name(key)))

    def _on_release(self, key: object) -> None:
        self._append(KeyEvent(type='key_released', key=_pynput_key_name(key)))

    def _append(self, event: KeyEvent) -> None:
        with self.lock:
            self.events.append(event)


def make_key_recorder(
    cfg: Cfg,
) -> NullKeyRecorder | TerminalKeyRecorder | PynputKeyRecorder:
    record_keys = cfg.keys.record_keys
    if cfg.console.gui or record_keys in (None, RecordKeys.none):
        return NullKeyRecorder()
    if cfg.keys.record_key_all_apps or record_keys == RecordKeys.all:
        return PynputKeyRecorder(record_keys)
    return TerminalKeyRecorder()


def _pynput_key_name(key: object) -> str:
    char = getattr(key, 'char', None)
    if isinstance(char, str) and char:
        return char.lower()
    name = getattr(key, 'name', None)
    if isinstance(name, str) and name:
        return name
    return str(key)
