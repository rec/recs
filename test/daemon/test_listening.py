import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from reccy.protocol import rpc

from recs.daemon import instances, listening
from recs.runtime.recording_control import RecordingControl
from recs.runtime.recording_control_protocol import (
    RecordingControlProtocol,
    RecordingControlTarget,
)


def test_listening_means_live_hardware_even_without_files() -> None:
    control = object.__new__(RecordingControl)
    control.runtime_state = SimpleNamespace(recording_paused=False)
    source = SimpleNamespace(is_alive=True, running=True)
    control.devices = SimpleNamespace(hardware={'mic': source})
    assert control.listening
    source.running = False
    assert not control.listening
    source.running = True
    control.runtime_state.recording_paused = True
    assert not control.listening


def test_listening_event_only_reports_changes() -> None:
    control = SimpleNamespace(listening=False)
    protocol = RecordingControlProtocol(cast(RecordingControlTarget, control))
    events: list[bool] = []
    external = SimpleNamespace(
        publish_event=lambda name, **data: events.append(data['listening'])
    )
    protocol.publish_listening(external)
    protocol.publish_listening(external)
    control.listening = True
    protocol.publish_listening(external)
    control.listening = False
    protocol.publish_listening(external)
    assert events == [False, True, False]


def test_combined_state_tracks_instances_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(instances, 'instances_directory', lambda: tmp_path)
    monkeypatch.setattr(listening.os, 'kill', lambda pid, signal: None)
    clients: list[object] = []
    active = False
    during_snapshot = False

    class Events:
        def __init__(self, endpoint: str, receive: object, **kwargs: object) -> None:
            self.receive = receive
            self.closed = False
            clients.append(self)

        def start(self) -> None:
            pass

        def wait_closed(self, timeout: float) -> bool:
            return self.closed

        def close(self) -> None:
            self.closed = True

    class Client:
        def __init__(self, endpoint: str, **kwargs: object) -> None:
            self.endpoint = endpoint

        def call(self, command: str) -> dict[str, object]:
            if during_snapshot:
                watcher.receive(
                    rpc.Event(name='listening_state', data={'listening': True})
                )
            return {
                'instance': descriptor.identity.model_dump(),
                'recording': {'listening': active},
            }

    monkeypatch.setattr(listening.rpc, 'EventClient', Events)
    monkeypatch.setattr(listening.rpc, 'Client', Client)
    descriptor = instances.InstanceDescriptor(
        identity=instances.InstanceIdentity(
            pid=123, started_at=1, start_token='one', role='local'
        ),
        control_endpoint='control',
        event_endpoint='events',
        protocol_version=1,
    )
    watcher = listening.ListeningWatcher()
    watcher.refresh()
    assert json.loads(capsys.readouterr().out)['listening'] is False
    path = tmp_path / 'one.json'
    path.write_text(descriptor.model_dump_json())
    watcher.refresh()
    assert json.loads(capsys.readouterr().out)['listening'] is False
    active = True
    watcher.receive(rpc.Event(name='listening_state'))
    watcher.refresh()
    assert json.loads(capsys.readouterr().out.splitlines()[-1])['listening'] is True
    active = False
    during_snapshot = True
    watcher.receive(rpc.Event(name='listening_state'))
    watcher.refresh()
    assert all(
        json.loads(v)['listening'] is None for v in capsys.readouterr().out.splitlines()
    )
    during_snapshot = False
    clients[0].closed = True
    watcher.refresh()
    assert json.loads(capsys.readouterr().out)['listening'] is None
    path.unlink()
    watcher.refresh()
    assert json.loads(capsys.readouterr().out)['listening'] is False
    watcher.close()
