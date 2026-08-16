import json
from pathlib import Path

from recs.ui import session_explain


def test_explain_reports_no_finished_files(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    report = session_explain.explain(manifest)

    assert report.explanations[0].reason == 'no files were recorded'


def test_explain_reports_manifest_warnings_and_pause(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"recording_paused","timestamp":"pause","reason":"disk space"}\n'
        '{"type":"warning","timestamp":"warn",'
        '"message":"Device Mic went offline"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    report = session_explain.explain(manifest)

    assert [explanation.reason for explanation in report.explanations] == [
        'no files were recorded',
        'selected device went offline',
        'recording paused',
    ]


def test_explain_reports_midi_source_failures(tmp_path: Path) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"midi_source_failed","timestamp":"fail",'
        '"midi_port":"Launchkey","value":"lost input"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    report = session_explain.explain(manifest)

    assert report.explanations[-1] == session_explain.Explanation(
        reason='MIDI input failed', evidence='lost input'
    )


def test_explain_prints_json(
    capsys,
    tmp_path: Path,
) -> None:
    manifest = tmp_path / 'recs-session.jsonl'
    manifest.write_text(
        '{"type":"header","version":2,"started_at":"start"}\n'
        '{"type":"footer","ended_at":"end","duration":1}\n'
    )

    assert session_explain.main(['--json', str(manifest)]) == 0

    assert json.loads(capsys.readouterr().out)['target'] == manifest.as_posix()


def test_explain_daemon_reports_paused_status(monkeypatch) -> None:
    monkeypatch.setattr(session_explain.rpc, 'Client', FakeRpcClient)

    report = session_explain.explain_daemon()

    assert report.explanations[0].reason == 'recording is paused'


def test_explain_daemon_reports_connection_error(monkeypatch) -> None:
    monkeypatch.setattr(session_explain.rpc, 'Client', BrokenRpcClient)

    report = session_explain.explain_daemon()

    assert report.explanations == [
        session_explain.Explanation(
            reason='daemon status unavailable', evidence='offline'
        )
    ]


class FakeRpcClient:
    def __init__(self, endpoint: object, *, role: str) -> None:
        self.endpoint = endpoint
        self.role = role

    def call(self, command: str) -> dict[str, object]:
        assert command == 'status_snapshot'
        return {'recording': {'paused': True, 'stopped': False}, 'errors': []}


class BrokenRpcClient:
    def __init__(self, endpoint: object, *, role: str) -> None:
        pass

    def call(self, command: str) -> dict[str, object]:
        raise ConnectionError('offline')
