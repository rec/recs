import json
import sys
import threading
import time
from collections.abc import Callable
from typing import Annotated, Protocol, cast

import tyro
from humanfriendly import format_size
from pydantic import BaseModel, ValidationError
from reccy.protocol import rpc
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from recs.ui import presentation

from . import paths


class Watch(BaseModel, frozen=True):
    json_output: Annotated[bool, tyro.conf.arg(name='--json')] = False


class EventConnection(Protocol):
    def start(self) -> None:
        ...

    def close(self) -> None:
        ...


class ControlConnection(Protocol):
    def call(self, command: str) -> str | dict[str, object]:
        ...


class StatusWatcher:
    def __init__(self, json_output: bool, output: Console | None = None) -> None:
        self.json_output = json_output
        self.output = output or Console()
        self.status: dict[str, object] = {}
        self.snapshot_time = time.monotonic()
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.live: Live | None = None
        self.pending: list[rpc.Event] | None = []

    def set_snapshot(self, status: dict[str, object]) -> None:
        with self.lock:
            self.status = status
            self.snapshot_time = time.monotonic()
            pending, self.pending = self.pending or [], None
        if self.json_output:
            print(json.dumps(status, separators=(',', ':')), flush=True)
        else:
            self.live = Live(
                self.renderable(), console=self.output, refresh_per_second=4
            )
            self.live.start(refresh=True)
        for event in pending:
            self.receive(event)

    def receive(self, event: rpc.Event) -> None:
        with self.lock:
            if self.pending is not None:
                self.pending.append(event)
                return
        if self.json_output:
            print(event.model_dump_json(), flush=True)
        if event.name == 'rows':
            with self.lock:
                self.status['rows'] = event.data.get('rows', [])
                self.status['errors'] = event.data.get('errors', [])
            if self.live is not None:
                self.live.update(self.renderable(), refresh=True)
        if event.name in {'shutdown', 'stopped'}:
            self.done.set()

    def renderable(self) -> Group:
        with self.lock:
            status = self.status.copy()
        rows = status.get('rows', [])
        table = Table(*presentation.COLUMNS)
        if isinstance(rows, list):
            view = presentation.view_model(cast(list[dict[str, object]], rows))
            for row in view.rows:
                table.add_row(*(cell.text for cell in row.cells))
        return Group(_summary(status, self.snapshot_time), table, _errors(status))

    def close(self) -> None:
        if self.live is not None:
            self.live.stop()


def watch(
    command: Watch,
    event_client: Callable[..., EventConnection] = rpc.EventClient,
    control_client: Callable[..., ControlConnection] = rpc.Client,
) -> int:
    watcher = StatusWatcher(command.json_output)
    events = event_client(
        paths.external_event_endpoint(),
        watcher.receive,
        role='recs-watch',
    )
    try:
        events.start()
        result = control_client(
            paths.external_control_endpoint(),
            role='recs-watch',
        ).call('status_snapshot')
        if not isinstance(result, dict):
            raise ConnectionError('Recs returned an invalid status snapshot')
        watcher.set_snapshot(result)
        watcher.done.wait()
    except (
        BrokenPipeError,
        ConnectionError,
        OSError,
        TimeoutError,
        ValidationError,
    ) as e:
        print(str(e) or type(e).__name__, file=sys.stderr)
        return 1
    finally:
        events.close()
        watcher.close()
    return 0


def main(argv: list[str]) -> int:
    return watch(
        tyro.cli(
            Watch,
            args=argv,
            prog='recs watch',
            description='Watch the running Recs daemon.',
        )
    )


def _summary(status: dict[str, object], snapshot_time: float) -> Panel:
    recording = status.get('recording', {})
    recording_data = (
        cast(dict[str, object], recording) if isinstance(recording, dict) else {}
    )
    paused = recording_data.get('paused')
    values = [f"recording: {'paused' if paused else 'active'}"]
    if session := status.get('session_directory'):
        values.append(f'session: {session}')
    if isinstance(disk := status.get('disk'), dict):
        disk_data = cast(dict[str, object], disk)
        if isinstance(free := disk_data.get('free_bytes'), (int, float)):
            values.append(f'disk free: {format_size(free)}')
        if isinstance(
            remaining := disk_data.get('estimated_seconds_remaining'), (int, float)
        ):
            remaining = max(0.0, remaining - (time.monotonic() - snapshot_time))
            values.append(f'disk remaining: {remaining:.0f}s')
    return Panel('\n'.join(values), title='Recs')


def _errors(status: dict[str, object]) -> Panel:
    messages: list[str] = []
    if isinstance(errors := status.get('errors'), list):
        for error in errors:
            if not isinstance(error, dict):
                continue
            error_data = cast(dict[str, object], error)
            if message := error_data.get('message'):
                suffix = f": {error_data['value']}" if 'value' in error_data else ''
                messages.append(f'{message}{suffix}')
    return Panel('\n'.join(messages) or 'None', title='Warnings')
