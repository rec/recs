import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_regressions.data_regression import DataRegressionFixture
from ufor import recording
from ufor.codec import score_toml
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from recs.recording import session_browser
from recs.recording.files import sealed_asset
from recs.recording.read import read_recording


def test_session_browser_lists_session_records(
    capsys,
    tmp_path: Path,
) -> None:
    session = _record(tmp_path)

    assert session_browser.main([str(tmp_path)]) == 0

    assert capsys.readouterr().out == (
        f'start  audio=1  midi=1  bytes=8  {session.as_posix()}\n'
    )


def test_session_browser_lists_session_records_as_json(
    capsys,
    tmp_path: Path,
) -> None:
    session = _record(tmp_path)

    assert session_browser.main(['--json', str(tmp_path)]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data == [
        {
            'path': session.as_posix(),
            'started_at': 'start',
            'ended_at': 'end',
            'duration': 1.5,
            'output_directories': [
                (session / 'audio').as_posix(),
                (session / 'midi').as_posix(),
            ],
            'devices': ['Mic'],
            'tracks': ['Mic:1'],
            'midi_ports': ['Launchkey'],
            'files': 2,
            'audio_files': 1,
            'midi_files': 1,
            'midi_messages': 3,
            'total_bytes': 8,
            'state': 'sealed',
            'unresolved_audio_files': 0,
            'warnings': ['quiet'],
            'disk_events': 1,
            'markers': 2,
            'continued_from': None,
            'continued_at': ['next/recording.toml'],
            'sources': ['Mic', 'audio:Mic:1', 'midi:Launchkey'],
            'marker_labels': ['g', 'solo'],
            'media_kinds': ['audio', 'midi'],
            'matched_filters': [],
        }
    ]


def test_session_browser_reports_invalid_records_and_keeps_healthy_sessions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    healthy = _record(tmp_path)
    directory = tmp_path / 'session'
    directory.mkdir(parents=True)
    record = directory / 'recording.toml'
    record.write_text('{')

    summaries = session_browser.scan(session_browser.SessionsCli(root=tmp_path))

    assert len(summaries) == 1
    assert summaries[0].path == healthy.as_posix()
    assert f'Cannot read recording {record}' in capsys.readouterr().err


def test_missing_journal_preserves_summary_with_diagnostic_warning(
    tmp_path: Path,
) -> None:
    session = _record(tmp_path)
    (session / 'session-record.jsonl').rename(session / 'moved-journal.jsonl')

    summary = session_browser.summarize(session)

    assert summary is not None
    assert summary.audio_files == 1
    assert summary.midi_messages == 3
    assert summary.warnings[0].startswith('Cannot read capture diagnostics:')


def test_session_browser_shows_one_session(
    capsys,
    tmp_path: Path,
) -> None:
    session = _record(tmp_path)

    assert session_browser.show([str(session)]) == 0

    output = capsys.readouterr().out
    assert 'audio_files: 1\n' in output
    assert 'midi_files: 1\n' in output
    assert 'midi_messages: 3\n' in output
    assert 'midi_ports: Launchkey\n' in output


def test_search_combines_filters_without_decoding_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data_regression: DataRegressionFixture,
) -> None:
    session = _record(tmp_path, started_at='2026-09-16T23:30:00-07:00')

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail('Session searches must not read audio payloads')

    monkeypatch.setattr('soundfile.SoundFile', unexpected)
    cfg = session_browser.SessionsCli(
        root=tmp_path,
        since=date(2026, 9, 16),
        before=date(2026, 9, 17),
        source='MIC',
        track='mic:1',
        marker='SOLO',
        media='midi',
        warning='QUIET',
    )
    summaries = session_browser.scan(cfg)
    assert [s.path for s in summaries] == [str(session)]
    data_regression.check({'matched_filters': summaries[0].matched_filters})


@pytest.mark.parametrize(
    'filters',
    [
        {'source': 'absent'},
        {'track': 'absent'},
        {'marker': 'absent'},
        {'media': 'osc'},
        {'warning': 'absent'},
        {'incomplete': True},
        {'since': date(2026, 9, 17)},
        {'before': date(2026, 9, 16)},
    ],
)
def test_each_search_filter_can_exclude_a_session(
    tmp_path: Path, filters: dict[str, object]
) -> None:
    _record(tmp_path, started_at='2026-09-16T12:00:00Z')
    cfg = session_browser.SessionsCli.model_validate({'root': tmp_path, **filters})
    assert session_browser.scan(cfg) == []


def test_unknown_capture_dates_are_excluded_only_when_date_filtering(
    tmp_path: Path,
) -> None:
    _record(tmp_path)
    assert len(session_browser.scan(session_browser.SessionsCli(root=tmp_path))) == 1
    assert (
        session_browser.scan(
            session_browser.SessionsCli(root=tmp_path, since=date(2026, 1, 1))
        )
        == []
    )


def test_search_survives_moving_root_and_reports_unreadable_entries(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / 'library'
    _record(root / 'b')
    _record(root / 'a')
    broken = root / 'z'
    broken.mkdir()
    (broken / 'recording.toml').write_bytes(b'\xff')
    cfg = session_browser.SessionsCli(root=root, marker='solo', limit=1)
    first = session_browser.scan(cfg)
    assert [Path(s.path).relative_to(root).as_posix() for s in first] == ['a/take']
    errors = capsys.readouterr().err
    assert 'utf-8' in errors
    assert str(broken / 'recording.toml') in errors
    assert 'Results limited to 1;' in errors
    moved = tmp_path / 'moved'
    root.rename(moved)
    second = session_browser.scan(cfg.model_copy(update={'root': moved}))
    assert [Path(s.path).relative_to(moved).as_posix() for s in second] == ['a/take']
    assert second[0].matched_filters == first[0].matched_filters
    assert 'utf-8' in capsys.readouterr().err


def test_search_finds_open_sessions_and_event_sources(tmp_path: Path) -> None:
    session = _record(tmp_path)
    path = session / 'recording.toml'
    document = read_recording(path)
    document = document.model_copy(
        update={
            'body': document.body.model_copy(update={'state': 'open', 'ended_at': None})
        }
    )
    path.write_text(score_toml(document))
    result = session_browser.scan(
        session_browser.SessionsCli(root=tmp_path, incomplete=True, source='launchkey')
    )
    assert len(result) == 1
    assert result[0].matched_filters[0] == 'source: midi:Launchkey'


def test_search_cli_reports_same_matches_in_text_and_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _record(tmp_path, started_at='2026-09-16T12:00:00Z')
    arguments = [
        str(tmp_path),
        '--since',
        '2026-09-16',
        '--marker',
        'solo',
        '--limit',
        '1',
    ]
    assert session_browser.main([*arguments, '--json']) == 0
    results = json.loads(capsys.readouterr().out)
    assert session_browser.main(arguments) == 0
    output = capsys.readouterr().out
    assert len(results) == 1
    for reason in results[0]['matched_filters']:
        assert f'matched: {reason}' in output


def test_search_rejects_reversed_dates_and_nonpositive_limits() -> None:
    with pytest.raises(ValidationError, match='before must be later'):
        session_browser.SessionsCli(since=date(2026, 9, 17), before=date(2026, 9, 16))
    with pytest.raises(ValidationError):
        session_browser.SessionsCli(limit=0)


def _record(tmp_path: Path, started_at: str = 'start') -> Path:
    session = tmp_path / 'take'
    audio = session / 'audio'
    midi = session / 'midi'
    audio.mkdir(parents=True)
    midi.mkdir()
    (audio / 'take.wav').write_bytes(b'data')
    (midi / 'keys.mid').write_bytes(b'midi')
    (session / 'session-record.jsonl').write_text(
        '{"type":"header","version":3,"started_at":"start"}\n'
        '{"type":"key_pressed","timestamp":"mark","key":"g"}\n'
        '{"type":"mark","timestamp":"mark","label":"solo"}\n'
        '{"type":"disk_switch_continued_at","timestamp":"switch",'
        '"continued_at":"next/session-record.jsonl"}\n'
        '{"type":"file_finished","media_type":"audio","stream_id":"audio:test:1","format":"wav","timestamp":"done","path":"audio/take.wav",'
        '"source":"Mic","track_name":"1","source_channels":[1],'
        '"channels":1,"sample_rate":48000,'
        '"bit_depth":32}\n'
        '{"type":"file_finished","media_type":"midi","stream_id":"midi:test","format":"smf","timestamp":"done",'
        '"path":"midi/keys.mid","source":"Launchkey","quantity_count":3,'
        '"midi_port":"Launchkey","timing_source":"mido"}\n'
        '{"type":"warning","timestamp":"warn","message":"quiet"}\n'
        '{"type":"footer","ended_at":"end","duration_seconds":1.5}\n'
    )
    value = recording.RecordingScore(
        name='take',
        title='Take',
        assets=[
            sealed_asset(session / p, session, i, e)
            for p, i, e in (
                ('session-record.jsonl', 'journal', 'recs-session-v3'),
                ('audio/take.wav', 'audio', 'wav'),
                ('midi/keys.mid', 'midi', 'smf'),
            )
        ],
        timebases=[Timebase(name='audio', rate=Rate(numerator=48000))],
        body=recording.Recording(
            state='sealed',
            started_at=started_at,
            ended_at='end',
            observed_duration_seconds=1.5,
            journal='journal',
            continued_at=['next/recording.toml'],
            streams=[
                recording.AudioStream(
                    name='mic',
                    source_id='audio:Mic:1',
                    source_name='Mic',
                    track_name='1',
                    end=48000,
                    stream=AudioType(timebase='audio', channels=['mono']),
                    fragments=[
                        recording.AudioFragment(asset='audio', start=0, count=48000)
                    ],
                ),
                recording.EventStream(
                    name='midi',
                    source_id='midi:Launchkey',
                    event_schema='midi',
                    fragments=[
                        recording.EventFragment(
                            asset='midi', event_count=3, timing='smf'
                        )
                    ],
                ),
            ],
        ),
    )
    (session / 'recording.toml').write_text(score_toml(value))
    return session
