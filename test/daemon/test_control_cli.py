from collections.abc import Iterator

import pytest

from recs.daemon import control_cli


class FakeClient:
    clients: list['FakeClient'] = []
    result: str | dict[str, object] = 'ok'
    error: OSError | None = None

    def __init__(self, endpoint: object, *, role: str, timeout: float) -> None:
        self.endpoint = endpoint
        self.role = role
        self.timeout = timeout
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.clients.append(self)

    def call(self, command: str, **params: object) -> str | dict[str, object]:
        self.calls.append((command, params))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture(autouse=True)
def reset_fake_client() -> Iterator[None]:
    FakeClient.clients = []
    FakeClient.result = 'ok'
    FakeClient.error = None
    yield


@pytest.mark.parametrize(
    ('arguments', 'rpc_command', 'params'),
    [
        (['status'], 'status_snapshot', {}),
        (['disk'], 'disk_status', {}),
        (['devices'], 'list_devices', {}),
        (['capabilities'], 'capabilities', {}),
        (['mutable'], 'mutable_attributes', {}),
        (
            ['get', 'recording.longest_file_time'],
            'get_cfg',
            {'address': 'recording.longest_file_time'},
        ),
        (['mark', 'solo starts'], 'mark', {'label': 'solo starts'}),
        (['pause'], 'pause_recording', {}),
        (['resume'], 'resume_recording', {}),
        (['calibrate'], 'calibrate', {}),
        (['card-replace'], 'card_replace', {}),
        (['reload-profiles'], 'reload_profiles', {}),
    ],
)
def test_control_commands_send_one_rpc_request(
    arguments: list[str],
    rpc_command: str,
    params: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(control_cli.rpc, 'Client', FakeClient)
    monkeypatch.setattr(
        control_cli.paths, 'external_control_endpoint', lambda: '/tmp/recs.sock'
    )

    assert control_cli.main(arguments) == 0

    assert len(FakeClient.clients) == 1
    client = FakeClient.clients[0]
    assert client.endpoint == '/tmp/recs.sock'
    assert client.role == 'recs-control'
    assert client.timeout == 6
    assert client.calls == [(rpc_command, params)]
    assert capsys.readouterr().out == '"ok"\n'


@pytest.mark.parametrize(
    ('value', 'parsed'),
    [
        ('3600', 3600),
        ('true', True),
        ('null', None),
        ('[1,2]', [1, 2]),
        ('{"source":"X18"}', {'source': 'X18'}),
        ('1h', '1h'),
        ('"3600"', '3600'),
    ],
)
def test_set_preserves_json_value_types(
    value: str,
    parsed: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(control_cli.rpc, 'Client', FakeClient)

    assert control_cli.main(['set', 'recording.longest_file_time', value]) == 0

    assert FakeClient.clients[0].calls == [
        (
            'set_cfg',
            {'address': 'recording.longest_file_time', 'value': parsed},
        )
    ]


def test_control_prints_json_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    FakeClient.result = {'type': 'cfg_value', 'value': 3600.0}
    monkeypatch.setattr(control_cli.rpc, 'Client', FakeClient)

    assert control_cli.main(['get', 'recording.longest_file_time']) == 0

    assert capsys.readouterr().out == '{"type":"cfg_value","value":3600.0}\n'


def test_control_reports_rpc_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    FakeClient.error = TimeoutError('RPC request timed out after 6s')
    monkeypatch.setattr(control_cli.rpc, 'Client', FakeClient)

    assert control_cli.main(['status']) == 1

    output = capsys.readouterr()
    assert output.out == ''
    assert output.err == 'RPC request timed out after 6s\n'
