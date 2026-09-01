import base64
import json
import socket
import time
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO

from reccy.jsonl import Compress
from threa import Runnable

from recs.base import times
from recs.cfg.cfg import Cfg
from recs.ui.session_record import (
    EventEntry,
    FileEntry,
    RecordEntry,
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
        write_entry: Callable[[RecordEntry], None],
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
        if not self.cfg.osc.osc_nodes.name:
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
        write_entry: Callable[[RecordEntry], None],
        write_error: Callable[[str, str], None] | None,
    ) -> None:
        self.node = node
        self.directory = session_directory
        self.warning = warning
        self.write_entry = write_entry
        self.write_error = write_error
        self.socket: socket.socket | None = None
        self.output: BinaryIO | None = None
        self.path: Path | None = None
        self.bytes_written = 0
        self.inbound_count = 0
        self.outbound_count = 0
        self.decode_error_count = 0
        self.last_packet_time: float | None = None
        self.last_error: str | None = None
        self.next_polls: list[float] = []
        self.next_subscriptions: list[float] = []
        self.compressor = Compress(key='kind') if node.jsonl_compression else None
        self.card_replace_backlog: list[dict[str, object]] = []
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
        for command in self.node.commands:
            if command.on_start:
                self._send(command, 'command')
        self.next_polls = [now for _ in self.node.polls]
        self.next_subscriptions = [now for _ in self.node.subscriptions]
        self.write_entry(
            EventEntry(
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
        for index, poll in enumerate(self.node.polls):
            if now >= self.next_polls[index]:
                self._send(poll, 'poll')
                self.next_polls[index] = now + poll.period
        for index, subscription in enumerate(self.node.subscriptions):
            if now >= self.next_subscriptions[index]:
                self._send(subscription, 'subscription')
                self.next_subscriptions[index] = now + subscription.resubscribe_period
        while True:
            try:
                data, source = self.socket.recvfrom(65_535)
            except BlockingIOError:
                return
            except OSError as error:
                self._fail('receive', str(error))
                return
            self.inbound_count += 1
            self.last_packet_time = times.timestamp()
            decoded = codec.decode_packet(data)
            self.decode_error_count += sum('error' in message for message in decoded)
            self._write_json(
                {
                    'time': self.last_packet_time,
                    'monotonic': time.monotonic(),
                    'direction': 'in',
                    'kind': 'osc',
                    'data_b64': base64.b64encode(data).decode('ascii'),
                    'decoded': decoded,
                    'source': [source[0], source[1]],
                }
            )

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
        self.output = self.path.open('ab')
        self.bytes_written = 0
        self.write_entry(
            FileEntry(
                type='file_started',
                kind='osc',
                timestamp=timestamp_to_json(times.timestamp()),
                path=self.path.name,
                source=self.node.name,
                osc_node=self.node.name,
            )
        )

    def close_output(self) -> None:
        if self.output is None or self.path is None:
            return
        self.output.close()
        self.output = None
        self.write_entry(
            FileEntry(
                type='file_finished',
                kind='osc',
                timestamp=timestamp_to_json(times.timestamp()),
                path=self.path.name,
                source=self.node.name,
                osc_node=self.node.name,
                inbound_count=self.inbound_count,
                outbound_count=self.outbound_count,
                decode_error_count=self.decode_error_count,
            )
        )

    def suspend_for_card_replace(self) -> None:
        self.close_output()
        self.card_replace_paused = True

    def suspend_after_unmount(self) -> None:
        self.output = None
        self.card_replace_paused = True

    def open_session(self, session_directory: Path) -> None:
        self.card_replace_paused = False
        self.open_output(session_directory)
        for record in self.card_replace_backlog:
            self._write_json(record)
        self.card_replace_backlog = []

    def _send(self, message: config.Command, reason: str) -> None:
        assert self.socket is not None
        assert self.node.host is not None
        assert self.node.port is not None
        data = codec.encode_message(message.path, message.args)
        target = (self.node.host, self.node.port)
        try:
            self.socket.sendto(data, target)
        except OSError as error:
            self._fail('send', str(error))
            self._write_json(
                {
                    'time': times.timestamp(),
                    'monotonic': time.monotonic(),
                    'direction': 'out',
                    'kind': 'error',
                    'target': [target[0], target[1]],
                    'error': str(error),
                    'reason': reason,
                }
            )
            return
        self.outbound_count += 1
        if message.record_success:
            self._write_json(
                {
                    'time': times.timestamp(),
                    'monotonic': time.monotonic(),
                    'direction': 'out',
                    'kind': 'osc',
                    'data_b64': base64.b64encode(data).decode('ascii'),
                    'decoded': codec.decode_packet(data),
                    'target': [target[0], target[1]],
                    'reason': reason,
                }
            )

    def _write_json(self, record: dict[str, object]) -> None:
        if self.card_replace_paused:
            self.card_replace_backlog.append(record)
            return
        if self.output is None:
            return
        if self.compressor is not None:
            record = next(self.compressor([record]))
        data = json.dumps(record, separators=(',', ':')).encode() + b'\n'
        try:
            if self.bytes_written and self.bytes_written + len(data) > MAX_FILE_BYTES:
                self.close_output()
                self.open_output(self.directory)
            assert self.output is not None
            self.output.write(data)
            self.output.flush()
            self.bytes_written += len(data)
        except OSError as error:
            if self.write_error is not None:
                self.write_error(self.node.name, str(error))
            self._fail('write', str(error))

    def _fail(self, operation: str, message: str) -> None:
        self.last_error = message
        self.warning(f'OSC node {self.node.name} {operation} failed: {message}')
        self.write_entry(
            EventEntry(
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
