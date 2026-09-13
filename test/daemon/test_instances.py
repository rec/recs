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
