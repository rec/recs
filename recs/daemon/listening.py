"""A fail-closed, all-instance state stream for remote consumers."""

import json
import os
import select
import sys
import threading
import time

from reccy.protocol import rpc

from . import instances


class ListeningWatcher:
    def __init__(self) -> None:
        self.clients: dict[str, rpc.EventClient] = {}
        self.descriptors: dict[str, instances.InstanceDescriptor] = {}
        self.lock = threading.Lock()
        self.generation = 0
        self.dirty = True
        self.state: bool | None = None
        self.last_snapshot = 0.0

    def receive(self, event: rpc.Event) -> None:
        if event.name in {'listening_state', 'shutdown', 'stopped'}:
            with self.lock:
                self.generation += 1
                self.dirty = True
                self.emit(None)

    def refresh(self) -> None:
        with self.lock:
            generation = self.generation
        descriptors: dict[str, instances.InstanceDescriptor] = {}
        try:
            for path in instances.instances_directory().glob('*.json'):
                descriptor = instances.InstanceDescriptor.model_validate_json(
                    path.read_text()
                )
                try:
                    os.kill(descriptor.identity.pid, 0)
                except ProcessLookupError:
                    continue
                descriptors[descriptor.identity.start_token] = descriptor
            changed = descriptors != self.descriptors
            self.descriptors = descriptors
            for key in list(self.clients):
                if key not in descriptors:
                    self.clients.pop(key).close()
            for key, descriptor in descriptors.items():
                if key not in self.clients:
                    client = rpc.EventClient(
                        descriptor.event_endpoint, self.receive, role='recs-listening'
                    )
                    self.clients[key] = client
                    client.start()
                if self.clients[key].wait_closed(0):
                    self.clients.pop(key).close()
                    raise ConnectionError('Recs event stream closed')
            if (
                not changed
                and not self.dirty
                and time.monotonic() - self.last_snapshot < 60
            ):
                with self.lock:
                    self.emit(self.state)
                return
            listening = False
            for descriptor in descriptors.values():
                snapshot = rpc.Client(
                    descriptor.control_endpoint, role='recs-listening', timeout=1
                ).call('status_snapshot')
                if not isinstance(snapshot, dict):
                    raise ConnectionError('Invalid recs snapshot')
                if snapshot.get('instance') != descriptor.identity.model_dump():
                    raise ValueError('Recs instance identity changed')
                recording = snapshot.get('recording')
                if (
                    not isinstance(recording, dict)
                    or type(recording.get('listening')) is not bool
                ):
                    raise ValueError('Recs does not report listening state')
                listening |= recording['listening']
            with self.lock:
                if self.generation == generation:
                    self.dirty = False
                    self.state = listening
                    self.last_snapshot = time.monotonic()
                    self.emit(listening)
        except (OSError, ValueError) as error:
            with self.lock:
                self.dirty = True
                self.emit(None)
            print(str(error), file=sys.stderr, flush=True)

    def emit(self, listening: bool | None) -> None:
        print(json.dumps({'listening': listening}, separators=(',', ':')), flush=True)

    def close(self) -> None:
        for client in self.clients.values():
            client.close()
        self.clients.clear()


def watch_listening() -> int:
    watcher = ListeningWatcher()
    try:
        while True:
            watcher.refresh()
            if select.select([sys.stdin], [], [], 1)[0] and not os.read(
                sys.stdin.fileno(), 1
            ):
                return 0
    finally:
        watcher.close()
