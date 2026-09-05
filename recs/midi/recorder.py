from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from time import monotonic
from typing import Protocol, cast

from threa import Runnable

from recs.base import times
from recs.base.types import MidiTiming
from recs.cfg.cfg import Cfg
from recs.ui.session_record import EventRecord, Record, timestamp_to_json

from . import device
from .writer import MidiMessage, MidiWriter

MIDI_DISCOVERY_INTERVAL_SECONDS = 10.0


class MidiPort(Protocol):
    def iter_pending(self) -> list[MidiMessage]:
        pass

    def close(self) -> None:
        pass


class MidiRecorder(Runnable):
    def __init__(
        self,
        cfg: Cfg,
        session_directory: Path,
        warning: Callable[[str], None],
        write_entry: Callable[[Record], None],
        *,
        write_error: Callable[[str, str], None] | None = None,
        input_names: Callable[[], list[str]] = device.input_names,
        open_input: Callable[[str], MidiPort] | None = None,
        timestamp: Callable[[], float] = times.timestamp,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self.cfg = cfg
        self.session_directory = session_directory
        self.warning = warning
        self.write_entry = write_entry
        self.write_error = write_error
        self.input_names = input_names
        self.open_input = open_input or _open_input
        self.timestamp = timestamp
        self.monotonic_clock = monotonic_clock
        self.ports: dict[str, MidiPort] = {}
        self.writers: dict[str, MidiWriter] = {}
        self.port_selectors: dict[str, str] = {}
        self.last_message_timestamp: dict[str, float] = {}
        self.failures: dict[str, tuple[str, float]] = {}
        self.card_replace_backlog: list[tuple[str, MidiMessage, float]] = []
        self.card_replace_paused = False
        self.next_discovery = float('-inf')
        super().__init__()

    def start(self) -> None:
        if not self.cfg.midi.record_midi:
            super().start()
            return
        self._discover(self.monotonic_clock())
        super().start()

    def stop(self) -> None:
        for name in list(self.ports):
            self._remove(name)
        super().stop()

    def close_session(self) -> None:
        for name, writer in list(self.writers.items()):
            try:
                self.write_entry(writer.finish())
            except OSError as error:
                self._record_write_error(name, error)
                self._record_failure(name, self._selector(name), str(error))
            self.writers.pop(name, None)

    def suspend_for_card_replace(self) -> None:
        self.close_session()
        self.card_replace_paused = True

    def suspend_after_unmount(self) -> None:
        self.writers = {}
        self.card_replace_paused = True

    def open_session(self, session_directory: Path) -> None:
        self.session_directory = session_directory
        for name in self.ports:
            self._new_writer(name, self.timestamp())
        self.card_replace_paused = False
        for name, message, timestamp in self.card_replace_backlog:
            if name not in self.writers:
                self._new_writer(name, timestamp)
            self.writers[name].record(message, timestamp)
        self.card_replace_backlog = []

    def poll(self) -> None:
        if not self.cfg.midi.record_midi:
            return
        if (now := self.monotonic_clock()) >= self.next_discovery:
            self._discover(now)
        for name, port in list(self.ports.items()):
            try:
                messages = list(port.iter_pending())
            except OSError as error:
                self._remove(name, failure=str(error))
                continue
            for message in messages:
                timestamp = self.timestamp()
                if self.card_replace_paused:
                    self.card_replace_backlog.append((name, message, timestamp))
                    self.last_message_timestamp[name] = timestamp
                    continue
                try:
                    self.writers[name].record(message, timestamp)
                except OSError as error:
                    self._remove(name, failure=str(error))
                    break
                self.last_message_timestamp[name] = timestamp

    def status(self) -> list[dict[str, object]]:
        states: list[dict[str, object]] = []
        for selector in self.cfg.midi.midi_include:
            names = [
                name for name in self.writers if self.port_selectors[name] == selector
            ]
            if names:
                timestamps = [
                    self.last_message_timestamp[name]
                    for name in names
                    if name in self.last_message_timestamp
                ]
                states.append(
                    {
                        'name': selector,
                        'selector': selector,
                        'port_name': None,
                        'state': 'recording',
                        'failed': False,
                        'message_count': sum(
                            self.writers[name].message_count for name in names
                        ),
                        'last_message_timestamp': max(timestamps, default=None),
                        'last_failure': None,
                        'last_failure_timestamp': None,
                    }
                )
                continue
            failure = self.failures.get(selector)
            states.append(
                {
                    'name': selector,
                    'selector': selector,
                    'port_name': None,
                    'state': 'failed' if failure else 'waiting',
                    'failed': failure is not None,
                    'message_count': 0,
                    'last_message_timestamp': None,
                    'last_failure': failure[0] if failure else None,
                    'last_failure_timestamp': failure[1] if failure else None,
                }
            )
        states.extend(
            {
                'name': name,
                'selector': self.port_selectors[name],
                'port_name': name,
                'state': 'recording',
                'failed': False,
                'message_count': self.writers[name].message_count,
                'last_message_timestamp': self.last_message_timestamp.get(name),
                'last_failure': None,
                'last_failure_timestamp': None,
            }
            for name in sorted(self.writers)
        )
        return states

    def _discover(self, now: float) -> None:
        self.next_discovery = now + MIDI_DISCOVERY_INTERVAL_SECONDS
        try:
            names = device.selected_inputs(self.cfg, self.input_names())
        except ModuleNotFoundError as error:
            if self.cfg.midi.midi_include:
                self.warning(f'MIDI inputs unavailable: {error}')
            return
        selected = set(names)
        for name in list(self.ports):
            if name not in selected:
                self._remove(name, stopped=True)
        for name in names:
            if name not in self.ports:
                self._open(name)

    def _open(self, name: str) -> None:
        port: MidiPort | None = None
        selector = self._selector(name)
        started_at = self.timestamp()
        try:
            port = self.open_input(name)
            writer = None
            if not self.card_replace_paused:
                writer = MidiWriter(
                    self.session_directory,
                    name,
                    cast(MidiTiming, self.cfg.midi.midi_timing),
                    started_at,
                )
        except (ModuleNotFoundError, OSError) as error:
            if port is not None:
                try:
                    port.close()
                except OSError:
                    pass
            self._record_failure(name, selector, str(error))
            return
        self.ports[name] = port
        if writer is not None:
            self.writers[name] = writer
        self.port_selectors[name] = selector
        self.failures.pop(selector, None)
        if writer is not None:
            self.write_entry(
                EventRecord(
                    timestamp=timestamp_to_json(started_at),
                    type='midi_source_started',
                    source=name,
                    timing_source=str(self.cfg.midi.midi_timing),
                    midi_port=name,
                )
            )
            self.write_entry(writer.start_entry())

    def _new_writer(self, name: str, started_at: float) -> None:
        self.writers[name] = MidiWriter(
            self.session_directory,
            name,
            cast(MidiTiming, self.cfg.midi.midi_timing),
            started_at,
        )
        self.write_entry(
            EventRecord(
                timestamp=timestamp_to_json(started_at),
                type='midi_source_started',
                source=name,
                timing_source=str(self.cfg.midi.midi_timing),
                midi_port=name,
            )
        )
        self.write_entry(self.writers[name].start_entry())

    def _remove(
        self,
        name: str,
        *,
        stopped: bool = False,
        failure: str | None = None,
    ) -> None:
        selector = self.port_selectors.pop(name, self._selector(name))
        errors = [failure] if failure else []
        if (port := self.ports.pop(name, None)) is not None:
            try:
                port.close()
            except OSError as error:
                errors.append(str(error))
        if (writer := self.writers.pop(name, None)) is not None:
            try:
                self.write_entry(writer.finish())
            except OSError as error:
                self._record_write_error(name, error)
                errors.append(str(error))
        self.last_message_timestamp.pop(name, None)
        if errors:
            self._record_failure(name, selector, ': '.join(errors))
        elif stopped:
            self.write_entry(
                EventRecord(
                    timestamp=timestamp_to_json(self.timestamp()),
                    type='midi_source_stopped',
                    source=name,
                    reason='disconnected',
                    midi_port=name,
                )
            )

    def _record_failure(self, name: str, selector: str, message: str) -> None:
        failure_time = self.timestamp()
        self.failures[selector] = (message, failure_time)
        self.warning(f'MIDI input {name} failed: {message}')
        self.write_entry(
            EventRecord(
                timestamp=timestamp_to_json(failure_time),
                type='midi_source_failed',
                source=name,
                value=message,
                midi_port=name,
            )
        )

    def _record_write_error(self, name: str, error: OSError) -> None:
        if self.write_error is not None:
            self.write_error(name, str(error))

    def _selector(self, name: str) -> str:
        return next(
            (
                selector
                for selector in self.cfg.midi.midi_include
                if name.startswith(selector)
            ),
            name,
        )


def _open_input(name: str) -> MidiPort:
    mido = import_module('mido')
    open_input = cast(Callable[[str], MidiPort], vars(mido)['open_input'])
    return open_input(name)
