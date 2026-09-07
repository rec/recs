import base64
import ipaddress
import queue
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter
from threa import Runnable

from recs.base import times
from recs.cfg.cfg import Cfg
from recs.model.events import Endpoint, OscDecodeError, OscEvent, OscMessage
from recs.model.time import Rate, Timebase
from recs.recording.events import EventWriter
from recs.ui.session_record import (
    EventRecord,
    Record,
    timestamp_to_json,
)

from . import codec, config

MAX_FILE_BYTES = 64 * 1024 * 1024


class OscRecorder(Runnable):
    def __init__(
        self,
        cfg: Cfg,
        session_directory: Path,
        warning: Callable[[str], None],
        write_entry: Callable[[Record], None],
        write_error: Callable[[str, str], None] | None = None,
    ) -> None:
        self.cfg = cfg
        self.session_directory = session_directory
        self.warning = warning
        self.write_entry = write_entry
        self.write_error = write_error
        self.nodes: dict[str, OscNodeRecorder] = {}
        super().__init__()

    def start(self) -> None:
        if not self.cfg.general.writes_files or not self.cfg.osc.osc_nodes.name:
            super().start()
            return
        try:
            nodes = config.load(self.cfg.osc.osc_nodes)
        except ValueError as error:
            self.warning(str(error))
            super().start()
            return
        for node in nodes:
            recorder = OscNodeRecorder(
                node,
                self.session_directory,
                self.warning,
                self.write_entry,
                self.write_error,
            )
            self.nodes[node.name] = recorder
            recorder.start()
        super().start()

    def stop(self) -> None:
        for node in self.nodes.values():
            node.stop()
        super().stop()

    def poll(self) -> None:
        for node in self.nodes.values():
            node.poll()

    def status(self) -> list[dict[str, object]]:
        return [self.nodes[name].status() for name in sorted(self.nodes)]

    def close_session(self) -> None:
        for node in self.nodes.values():
            node.close_output()

    def suspend_for_card_replace(self) -> None:
        for node in self.nodes.values():
            node.suspend_for_card_replace()

    def suspend_after_unmount(self) -> None:
        for node in self.nodes.values():
            node.suspend_after_unmount()

    def open_session(self, session_directory: Path) -> None:
        self.session_directory = session_directory
        for node in self.nodes.values():
            node.open_session(session_directory)


class OscNodeRecorder:
    def __init__(
        self,
        node: config.Node,
        session_directory: Path,
        warning: Callable[[str], None],
        write_entry: Callable[[Record], None],
        write_error: Callable[[str, str], None] | None,
    ) -> None:
        self.node = node
        self.directory = session_directory
        self.warning = warning
        self.write_entry = write_entry
        self.write_error = write_error
        self.socket: socket.socket | None = None
        self.target: tuple[str, int] | None = None
        self.resolved_targets: queue.SimpleQueue[
            tuple[tuple[str, int] | None, str | None]
        ] = queue.SimpleQueue()
        self.writer: EventWriter | None = None
        self.ordinal = 0
        self.path: Path | None = None
        self.bytes_written = 0
        self.inbound_count = 0
        self.outbound_count = 0
        self.decode_error_count = 0
        self.last_packet_time: float | None = None
        self.last_error: str | None = None
        self.next_polls: list[float] = []
        self.next_subscriptions: list[float] = []
        self.card_replace_backlog: list[OscEvent] = []
        self.card_replace_paused = False

    def start(self) -> None:
        try:
            self.open_output(self.directory)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind(('', self.node.bind_port))
            self.socket.setblocking(False)
        except OSError as error:
            self._fail('start', str(error))
            return
        now = time.monotonic()
        if self.node.host is not None and self.node.port is not None:
            try:
                ipaddress.IPv4Address(self.node.host)
            except ipaddress.AddressValueError:
                threading.Thread(
                    target=self._resolve_target,
                    daemon=True,
                    name=f'OscResolve-{self.node.name}',
                ).start()
            else:
                self.target = (self.node.host, self.node.port)
                self._start_outbound(now)
        self.write_entry(
            EventRecord(
                type='osc_node_started',
                timestamp=timestamp_to_json(times.timestamp()),
                source=self.node.name,
                path=self.path.name if self.path is not None else None,
                address=self._address(),
            )
        )

    def stop(self) -> None:
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.close_output()

    def poll(self) -> None:
        if self.socket is None:
            return
        now = time.monotonic()
        self._receive_resolved_target(now)
        if self.target is not None:
            for index, poll in enumerate(self.node.polls):
                if now >= self.next_polls[index]:
                    self._send(poll, 'poll')
                    self.next_polls[index] = now + poll.period
            for index, subscription in enumerate(self.node.subscriptions):
                if now >= self.next_subscriptions[index]:
                    self._send(subscription, 'subscription')
                    self.next_subscriptions[index] = (
                        now + subscription.resubscribe_period
                    )
        while True:
            try:
                data, source = self.socket.recvfrom(65_535)
                received_tick = time.monotonic_ns()
            except BlockingIOError:
                return
            except OSError as error:
                self._fail('receive', str(error))
                return
            self.inbound_count += 1
            self.last_packet_time = times.timestamp()
            decoded = codec.decode_packet(data)
            self.decode_error_count += sum('error' in message for message in decoded)
            self._capture(data, 'in', source, received_tick)

    def status(self) -> dict[str, object]:
        return {
            'name': self.node.name,
            'state': 'error' if self.last_error else 'running',
            'path': str(self.path) if self.path else None,
            'size': self.bytes_written,
            'inbound_count': self.inbound_count,
            'outbound_count': self.outbound_count,
            'decode_error_count': self.decode_error_count,
            'last_packet_time': self.last_packet_time,
            'last_error': self.last_error,
        }

    def open_output(self, session_directory: Path) -> None:
        self.directory = session_directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = _next_path(self.directory, self.node.name)
        self.writer = EventWriter(
            self.path,
            self.node.name,
            'osc',
            Timebase(id='monotonic', rate=Rate(numerator=1_000_000_000)),
            'host_monotonic_packet_observation',
            time.monotonic_ns(),
        )
        self.bytes_written = 0
        self.write_entry(self.writer.start_entry())

    def close_output(self) -> None:
        if self.writer is None:
            return
        self.write_entry(self.writer.finish())
        self.writer = None

    def suspend_for_card_replace(self) -> None:
        self.close_output()
        self.card_replace_paused = True

    def suspend_after_unmount(self) -> None:
        self.writer = None
        self.card_replace_paused = True

    def open_session(self, session_directory: Path) -> None:
        self.card_replace_paused = False
        self.open_output(session_directory)
        for record in self.card_replace_backlog:
            self._write_event(record)
        self.card_replace_backlog = []

    def _send(self, message: config.Command, reason: str) -> None:
        assert self.socket is not None
        assert self.target is not None
        data = codec.encode_message(message.path, message.args)
        try:
            self.socket.sendto(data, self.target)
        except OSError as error:
            self._fail('send', str(error))
            return
        self.outbound_count += 1
        if message.record_success:
            self._capture(data, 'out', self.target, time.monotonic_ns(), reason)

    def _resolve_target(self) -> None:
        assert self.node.host is not None
        assert self.node.port is not None
        try:
            address = socket.getaddrinfo(
                self.node.host,
                self.node.port,
                family=socket.AF_INET,
                type=socket.SOCK_DGRAM,
            )[0][4]
        except OSError as error:
            self.resolved_targets.put((None, str(error)))
            return
        host, port = address[0], address[1]
        assert isinstance(host, str)
        assert isinstance(port, int)
        self.resolved_targets.put(((host, port), None))

    def _receive_resolved_target(self, now: float) -> None:
        try:
            target, error = self.resolved_targets.get_nowait()
        except queue.Empty:
            return
        if error is not None:
            self._fail('resolve', error)
            return
        assert target is not None
        self.target = target
        self._start_outbound(now)

    def _start_outbound(self, now: float) -> None:
        for command in self.node.commands:
            if command.on_start:
                self._send(command, 'command')
        self.next_polls = [now for _ in self.node.polls]
        self.next_subscriptions = [now for _ in self.node.subscriptions]

    def _capture(
        self,
        data: bytes,
        direction: Literal['in', 'out'],
        endpoint: tuple[str, int],
        tick: int,
        reason: str | None = None,
    ) -> None:
        event = OscEvent(
            tick=tick,
            ordinal=self.ordinal,
            data_b64=base64.b64encode(data).decode('ascii'),
            direction=direction,
            source_time=timestamp_to_json(times.timestamp()),
            endpoint=Endpoint(host=endpoint[0], port=endpoint[1]),
            decoded=TypeAdapter(list[OscMessage | OscDecodeError]).validate_python(
                codec.decode_packet(data)
            ),
            reason=reason,
        )
        self.ordinal += 1
        self._write_event(event)

    def _write_event(self, event: OscEvent) -> None:
        if self.card_replace_paused:
            self.card_replace_backlog.append(event)
            return
        if self.writer is None:
            return
        size = len(event.model_dump_json(exclude_none=True).encode()) + 1
        try:
            if self.bytes_written and self.bytes_written + size > MAX_FILE_BYTES:
                self.close_output()
                self.open_output(self.directory)
            assert self.writer is not None
            self.writer.write(event)
            self.bytes_written += size
        except OSError as error:
            if self.write_error is not None:
                self.write_error(self.node.name, str(error))
            self._fail('write', str(error))

    def _fail(self, operation: str, message: str) -> None:
        self.last_error = message
        self.warning(f'OSC node {self.node.name} {operation} failed: {message}')
        self.write_entry(
            EventRecord(
                type='osc_node_failed',
                timestamp=timestamp_to_json(times.timestamp()),
                source=self.node.name,
                value=message,
                reason=operation,
            )
        )

    def _address(self) -> str:
        if self.socket is None:
            return ''
        host, port = self.socket.getsockname()
        return f'{host}:{port}'


def _next_path(directory: Path, name: str) -> Path:
    path = directory / f'{name}.jsonl'
    index = 1
    while path.exists():
        path = directory / f'{name}-{index}.jsonl'
        index += 1
    return path
