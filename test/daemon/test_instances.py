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
        protocol_version=11,
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
        protocol_version=11,
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


def test_selector_arguments_reject_zero_and_conflicting_targets() -> None:
    assert instances.selector_arguments(['--instance', '-2', 'pause']) == (
        instances.Selector(instance=-2),
        ['pause'],
    )

    for arguments, message in [
        (['--instance', '0', 'pause'], 'cannot be zero'),
        (['--daemon', '--instance', '1', 'pause'], 'cannot be used together'),
    ]:
        try:
            instances.selector_arguments(arguments)
        except ValueError as error:
            assert message in str(error)
        else:
            raise AssertionError('selector was accepted')


def test_resolve_prefers_newest_local_and_uses_daemon_as_fallback(
    monkeypatch,
) -> None:
    daemon = _descriptor('daemon', 300, 1)
    older = _descriptor('local', 100, 2)
    newest = _descriptor('local', 200, 3)
    monkeypatch.setattr(instances, 'discover', lambda: [newest, older, daemon])
    monkeypatch.setattr(instances, 'external_control_endpoint', lambda: '/tmp/daemon')
    monkeypatch.setattr(instances, 'external_event_endpoint', lambda: '/tmp/events')

    assert instances.resolve(instances.Selector()).identity == newest.identity
    assert instances.resolve(instances.Selector(instance=-2)).identity == older.identity
    assert (
        instances.resolve(instances.Selector(instance=300)).identity == daemon.identity
    )
    assert (
        instances.resolve(instances.Selector(daemon=True)).control_endpoint
        == '/tmp/daemon'
    )


def test_resolve_reports_available_instances_when_selector_is_unavailable(
    monkeypatch,
) -> None:
    descriptor = _descriptor('local', 100, 2)
    monkeypatch.setattr(instances, 'discover', lambda: [descriptor])

    try:
        instances.resolve(instances.Selector(instance=-2))
    except ValueError as error:
        assert str(error) == (
            'Recs instance -2 is unavailable. Live instances: local PID 100'
        )
    else:
        raise AssertionError('selector was accepted')


def test_settings_writer_finds_only_a_live_matching_destination(monkeypatch) -> None:
    match = _descriptor('local', 100, 2).model_copy(
        update={'settings_path': '/tmp/second-interface.json'}
    )
    other = _descriptor('local', 200, 3).model_copy(
        update={'settings_path': '/tmp/other.json'}
    )
    monkeypatch.setattr(instances, 'discover', lambda: [other, match])

    assert instances.settings_writer('/tmp/second-interface.json') == match
    assert instances.settings_writer('/tmp/missing.json') is None


def test_source_users_excludes_the_current_instance(monkeypatch) -> None:
    current = _descriptor('local', 100, 2)
    other = _descriptor('daemon', 200, 3).model_copy(update={'sources': ['Mic']})
    monkeypatch.setattr(instances, 'discover', lambda: [current, other])

    assert instances.source_users('Mic', current.identity) == [other]


def test_settings_claim_excludes_another_live_instance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = instances.InstanceIdentity(
        pid=100,
        start_token='first',
        started_at=1,
        role='local',
    )
    second = first.model_copy(update={'pid': 200, 'start_token': 'second'})
    monkeypatch.setattr(instances, '_process_exists', lambda pid: True)

    instances.claim_settings('/tmp/second-interface.json', first, tmp_path)

    try:
        instances.claim_settings('/tmp/second-interface.json', second, tmp_path)
    except ValueError as error:
        assert str(error) == 'Recs PID 100 is already saving /tmp/second-interface.json'
    else:
        raise AssertionError('settings claim was accepted')

    instances.release_settings('/tmp/second-interface.json', first, tmp_path)

    assert instances.claim_settings(
        '/tmp/second-interface.json', second, tmp_path
    ).exists()


def _descriptor(
    role: instances.InstanceRole,
    pid: int,
    started_at: int,
) -> instances.InstanceDescriptor:
    return instances.InstanceDescriptor(
        identity=instances.InstanceIdentity(
            pid=pid,
            start_token=f'token-{pid}',
            started_at=started_at,
            role=role,
        ),
        control_endpoint=f'/tmp/{pid}.sock',
        event_endpoint=f'/tmp/{pid}-events.sock',
        protocol_version=11,
    )
