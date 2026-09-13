from pathlib import Path

from reccy.services import models

from recs.daemon import instances


def test_local_endpoints_and_descriptor_include_process_identity(
    tmp_path: Path,
) -> None:
    identity = instances.InstanceIdentity(
        pid=43120,
        start_token='abc123',
        started_at=1_789_314_000_000_000_000,
        role='local',
        profile='second-interface',
    )

    assert instances.local_control_endpoint(identity, tmp_path) == (
        tmp_path / '.local/state/recs/instances/43120-abc123/control.sock'
    )
    assert instances.local_event_endpoint(identity, tmp_path) == (
        tmp_path / '.local/state/recs/instances/43120-abc123/events.sock'
    )
    assert instances.descriptor_path(identity, tmp_path) == (
        tmp_path / '.local/state/recs/instances/43120-abc123.json'
    )


def test_windows_instance_endpoints_are_unique_named_pipes(tmp_path: Path) -> None:
    identity = instances.InstanceIdentity(
        pid=43120,
        start_token='abc123',
        started_at=1,
        role='local',
    )

    assert (
        instances.local_control_endpoint(identity, tmp_path, models.Platform.windows)
        == r'\\.\pipe\recs-43120-abc123-control'
    )
    assert (
        instances.local_event_endpoint(identity, tmp_path, models.Platform.windows)
        == r'\\.\pipe\recs-43120-abc123-events'
    )


def test_publish_and_remove_instance_descriptor(tmp_path: Path) -> None:
    descriptor = instances.InstanceDescriptor(
        identity=instances.InstanceIdentity(
            pid=43120,
            start_token='abc123',
            started_at=1,
            role='local',
        ),
        control_endpoint='/tmp/recs-control.sock',
        event_endpoint='/tmp/recs-events.sock',
        protocol_version=9,
        sources=['Mic'],
    )

    path = instances.publish(descriptor, tmp_path)

    assert (
        instances.InstanceDescriptor.model_validate_json(path.read_text()) == descriptor
    )

    instances.remove(descriptor.identity, tmp_path)

    assert not path.exists()


def test_discover_accepts_only_the_instance_described_by_its_endpoint(
    tmp_path: Path,
) -> None:
    live = instances.InstanceDescriptor(
        identity=instances.InstanceIdentity(
            pid=43120,
            start_token='live',
            started_at=2,
            role='local',
        ),
        control_endpoint='/tmp/live.sock',
        event_endpoint='/tmp/live-events.sock',
        protocol_version=9,
    )
    stale = live.model_copy(
        update={
            'identity': live.identity.model_copy(
                update={'start_token': 'stale', 'started_at': 1}
            ),
            'control_endpoint': '/tmp/stale.sock',
        }
    )
    instances.publish(live, tmp_path)
    instances.publish(stale, tmp_path)

    class Client:
        def __init__(self, endpoint: str, *, role: str, timeout: float) -> None:
            self.endpoint = endpoint

        def call(self, command: str) -> dict[str, object]:
            assert command == 'capabilities'
            return {'instance': live.identity.model_dump()}

    assert instances.discover(tmp_path, client=Client) == [live]
