from __future__ import annotations

import json
import unittest
from collections.abc import Iterator

from recs.cfg.cfg import Cfg
from recs.daemon import gui_ipc, gui_protocol
from recs.ui.key_events import KeyEvent


class RecsProtocolTests(unittest.TestCase):
    def test_recs_handles_hello_key_events_and_calibrate_request(self) -> None:
        key_events: list[KeyEvent] = []

        def respond(request: gui_ipc.ControlRequest) -> None:
            request.respond(
                gui_protocol.Calibrated(
                    type='calibrated',
                    measurements={},
                    noise_floors={'Mic': {'noise_floor': 15.0}},
                )
            )

        connection = FakeConnection(
            [
                json.dumps(
                    {'type': 'hello', 'role': 'gui', 'version': gui_protocol.VERSION}
                )
                + '\n',
                '{"type":"key_pressed","key":"g"}\n',
                '{"type":"key_released","key":"g"}\n',
                '{"type":"calibrate"}\n',
            ]
        )
        listener = gui_ipc.GuiListener(
            connection,
            key_events.append,
            respond,
        )

        listener._read()

        self.assertEqual(
            [json.loads(message) for message in connection.sent],
            [
                {'type': 'hello', 'role': 'daemon', 'version': gui_protocol.VERSION},
                {
                    'type': 'calibrated',
                    'measurements': {},
                    'noise_floors': {'Mic': {'noise_floor': 15.0}},
                },
            ],
        )
        self.assertEqual(
            key_events,
            [
                KeyEvent(type='key_pressed', key='g'),
                KeyEvent(type='key_released', key='g'),
            ],
        )

    def test_recs_rejects_requests_before_hello(self) -> None:
        connection = FakeConnection(['{"type":"calibrate"}\n'])
        listener = gui_ipc.GuiListener(connection, lambda event: None)

        listener._read()

        self.assertEqual(
            [json.loads(message) for message in connection.sent],
            [
                {
                    'type': 'error',
                    'message': 'GUI hello required before other messages',
                }
            ],
        )
        self.assertTrue(connection.closed)

    def test_recs_rejects_unsupported_protocol_versions(self) -> None:
        connection = FakeConnection(['{"type":"hello","role":"gui","version":1}\n'])
        listener = gui_ipc.GuiListener(connection, lambda event: None)

        listener._read()

        self.assertEqual(
            [json.loads(message) for message in connection.sent],
            [
                {
                    'type': 'error',
                    'message': (
                        'GUI protocol version 1 is not supported; daemon requires '
                        f'{gui_protocol.VERSION}'
                    ),
                }
            ],
        )
        self.assertTrue(connection.closed)

    def test_recs_sends_rows_messages(self) -> None:
        server = gui_ipc.DaemonGuiServer(lambda: iter([{'device': 'Mic'}]), Cfg())
        listener = FakeListener()
        server.clients = [listener]

        server.broadcast([{'device': 'Mic'}], [])

        self.assertEqual(
            [json.loads(message) for message in listener.messages],
            [{'type': 'rows', 'rows': [{'device': 'Mic'}], 'errors': []}],
        )


class FakeConnection:
    def __init__(self, received: list[str]) -> None:
        self.received = received
        self.sent: list[str] = []
        self.closed = False

    def read_lines(self) -> Iterator[str]:
        return iter(self.received)

    def write(self, message: str) -> bool:
        self.sent.append(message)
        return True

    def close(self) -> None:
        self.closed = True


class FakeListener:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def write(self, message: str) -> bool:
        self.messages.append(message)
        return True

    def close(self) -> None:
        pass


if __name__ == '__main__':
    unittest.main()
