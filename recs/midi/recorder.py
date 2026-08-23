from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from threa import Runnable

from recs.base import times
from recs.base.types import MidiTiming
from recs.cfg.cfg import Cfg
from recs.ui.session_manifest import ManifestEvent, ManifestRecord, timestamp_to_json

from . import device
from .writer import MidiMessage, MidiWriter


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
        write_record: Callable[[ManifestRecord], None],
        *,
        input_names: Callable[[], list[str]] = device.input_names,
        open_input: Callable[[str], MidiPort] | None = None,
        timestamp: Callable[[], float] = times.timestamp,
    ) -> None:
        self.cfg = cfg
        self.session_directory = session_directory
        self.warning = warning
        self.write_record = write_record
        self.input_names = input_names
        self.open_input = open_input or _open_input
        self.timestamp = timestamp
        self.ports: dict[str, MidiPort] = {}
        self.writers: dict[str, MidiWriter] = {}
        self.last_message_timestamp: dict[str, float] = {}
        self.failed: set[str] = set()
        self.started = False
        super().__init__()

    def start(self) -> None:
        if not self.cfg.midi.record_midi:
            super().start()
            return
        self.started = True
        self._discover()
        super().start()

    def stop(self) -> None:
        for name, port in list(self.ports.items()):
            try:
                port.close()
            except OSError as e:
                self.warning(f'MIDI input {name} did not close: {e}')
        self.ports.clear()
        for name, writer in sorted(self.writers.items()):
            try:
                self.write_record(writer.finish())
            except OSError as e:
                self.warning(f'MIDI file for {name} was not written: {e}')
        self.writers.clear()
        super().stop()

    def poll(self) -> None:
        self._discover()
        for name, port in list(self.ports.items()):
            try:
                messages = list(port.iter_pending())
            except OSError as e:
                self._fail(name, str(e))
                continue
            for message in messages:
                timestamp = self.timestamp()
                self.writers[name].record(message, timestamp)
                self.last_message_timestamp[name] = timestamp

    def status(self) -> list[dict[str, object]]:
        states = [
            {
                'name': name,
                'state': 'recording',
                'failed': name in self.failed,
                'message_count': self.writers[name].message_count,
                'last_message_timestamp': self.last_message_timestamp.get(name),
            }
            for name in sorted(self.writers)
        ]
        states.extend(
            {
                'name': name,
                'state': 'waiting',
                'failed': False,
                'message_count': 0,
                'last_message_timestamp': None,
            }
            for name in self.cfg.midi.midi_include
            if not any(value.startswith(name) for value in self.writers)
        )
        return states

    def _discover(self) -> None:
        try:
            names = device.selected_inputs(self.cfg, self.input_names())
        except ModuleNotFoundError as error:
            if self.cfg.midi.midi_include:
                self.warning(f'MIDI inputs unavailable: {error}')
            return
        for name in names:
            if name not in self.ports:
                self._open(name)

    def _open(self, name: str) -> None:
        try:
            self.ports[name] = self.open_input(name)
        except (ModuleNotFoundError, OSError) as e:
            self._fail(name, str(e))
            return
        self.writers[name] = MidiWriter(
            self.session_directory,
            name,
            cast(MidiTiming, self.cfg.midi.midi_timing),
        )
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(self.timestamp()),
                type='midi_source_started',
                source=name,
                timing_source=str(self.cfg.midi.midi_timing),
                midi_port=name,
            )
        )

    def _fail(self, name: str, message: str) -> None:
        self.failed.add(name)
        if (port := self.ports.pop(name, None)) is not None:
            port.close()
        if (writer := self.writers.pop(name, None)) is not None:
            self.write_record(writer.finish())
        self.warning(f'MIDI input {name} failed: {message}')
        self.write_record(
            ManifestEvent(
                timestamp=timestamp_to_json(self.timestamp()),
                type='midi_source_failed',
                source=name,
                value=message,
                midi_port=name,
            )
        )


def _open_input(name: str) -> MidiPort:
    mido = import_module('mido')
    open_input = cast(Callable[[str], MidiPort], vars(mido)['open_input'])
    return open_input(name)
