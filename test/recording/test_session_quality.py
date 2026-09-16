import json
from pathlib import Path

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from ufor import recording
from ufor.codec import score_toml
from ufor.streams import AudioType
from ufor.time import Rate, TickRange, Timebase

from recs.recording import audio_quality, session_quality
from recs.recording.files import sealed_asset
from recs.recording.read import read_recording


@pytest.fixture
def session(tmp_path: Path) -> Path:
    audio = np.zeros((96_000, 2), dtype=np.float32)
    audio[:, 1] = 0.0001
    audio[12_000:12_002, 0] = 1
    audio[59_998:60_004, 0] = -1
    audio[90_000:, 0] = 1
    soundfile.write(tmp_path / 'take.wav', audio, 48_000, subtype='FLOAT')
    (tmp_path / 'session-record.jsonl').write_text(
        '{"type":"header","version":4,"started_at":"start"}\n'
        '{"type":"source_offline","timestamp":"later","source":"Mic"}\n'
        '{"type":"buffer_overflow","timestamp":"later","source":"Mic"}\n'
    )
    document = recording.RecordingScore(
        name='quality-test',
        title='Quality test',
        assets=[
            sealed_asset(tmp_path / 'take.wav', tmp_path, 'audio', 'wav'),
            sealed_asset(
                tmp_path / 'session-record.jsonl',
                tmp_path,
                'journal',
                'recs-session-v4',
            ),
        ],
        timebases=[Timebase(name='mic-clock', rate=Rate(numerator=48_000))],
        body=recording.Recording(
            state='open',
            started_at='start',
            journal='journal',
            unfinished_files=[
                recording.UnfinishedFile(
                    source_id='Mic',
                    journal_path='unfinished.wav',
                    observed_opened_at='later',
                )
            ],
            streams=[
                recording.AudioStream(
                    name='mic',
                    source_id='Mic',
                    source_name='Microphone',
                    track_name='Stereo',
                    stream=AudioType(timebase='mic-clock', channels=['left', 'right']),
                    end=108_000,
                    fragments=[
                        recording.AudioFragment(
                            asset='audio',
                            asset_start=12_000,
                            start=24_000,
                            count=72_000,
                        )
                    ],
                    gaps=[
                        recording.Gap(
                            start=0,
                            end=12_000,
                            reason=recording.GapReason.silence_suppressed,
                        ),
                        recording.Gap(
                            start=12_000,
                            end=24_000,
                            reason=recording.GapReason.input_overflow,
                        ),
                        recording.Gap(
                            start=96_000,
                            end=108_000,
                            reason=recording.GapReason.disconnected,
                        ),
                    ],
                )
            ],
        ),
    )
    (tmp_path / 'recording.toml').write_text(score_toml(document))
    return tmp_path


def test_metadata_distinguishes_gaps_without_reading_audio(
    session: Path,
    monkeypatch: pytest.MonkeyPatch,
    data_regression: DataRegressionFixture,
) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail('Metadata inspection must not decode audio')

    monkeypatch.setattr(soundfile, 'SoundFile', unexpected)
    report = session_quality.inspect(session)
    data = report.model_dump(mode='json')
    data['path'] = 'recording.toml'
    data_regression.check(data)


def test_bounded_analysis_locates_runs_and_preserves_media(
    session: Path, data_regression: DataRegressionFixture
) -> None:
    before = {p.name: p.read_bytes() for p in session.iterdir()}
    report = session_quality.inspect(
        session, audio_quality.AnalysisSettings(max_seconds=1.25)
    )
    measurement = report.tracks[0].audio[0]
    assert {p.name: p.read_bytes() for p in session.iterdir()} == before
    data_regression.check(measurement.model_dump(mode='json'), round_digits=12)
    assert (
        sum(
            f.kind == 'near_full_scale' and f.severity == 'advisory'
            for f in report.findings
        )
        == 1
    )
    assert not any('quiet' in f.kind for f in report.findings)


def test_unmapped_audio_never_claims_source_positions(
    session: Path, data_regression: DataRegressionFixture
) -> None:
    path = session / 'recording.toml'
    document = read_recording(path)
    stream = document.body.streams[0]
    assert isinstance(stream, recording.AudioStream)
    stream = stream.model_copy(
        update=dict(
            fragments=[],
            gaps=[],
            end=100_000,
            unmapped_fragments=[
                recording.UnmappedAudioFragment(
                    asset='audio',
                    count=96_000,
                    journal_range=TickRange(start=0, end=100_000),
                )
            ],
        )
    )
    document = document.model_copy(
        update={'body': document.body.model_copy(update={'streams': [stream]})}
    )
    path.write_text(score_toml(document))
    report = session_quality.inspect(
        path, audio_quality.AnalysisSettings(max_seconds=1.5)
    )
    track = report.tracks[0]
    assert track.captured_frames == 0
    assert track.unresolved_frames == 96_000
    finding = next(f for f in report.findings if f.kind == 'unresolved_placement')
    assert finding.start_frame is finding.end_frame is None
    data_regression.check(track.audio[0].model_dump(mode='json'), round_digits=12)


def test_variants_do_not_double_captured_duration(session: Path) -> None:
    path = session / 'recording.toml'
    document = read_recording(path)
    stream = document.body.streams[0]
    assert isinstance(stream, recording.AudioStream)
    fragment = stream.fragments[0].model_copy(update={'variant_group': 'variants'})
    stream = stream.model_copy(
        update={
            'fragments': [
                fragment,
                fragment.model_copy(update={'asset': 'alternative'}),
            ]
        }
    )
    document = document.model_copy(
        update={
            'assets': [
                *document.assets,
                document.assets[0].model_copy(update={'name': 'alternative'}),
            ],
            'body': document.body.model_copy(update={'streams': [stream]}),
        }
    )
    path.write_text(score_toml(document))
    assert session_quality.inspect(path).tracks[0].captured_frames == 72_000


def test_threshold_and_run_limit_are_explicit(session: Path) -> None:
    report = session_quality.inspect(
        session,
        audio_quality.AnalysisSettings(
            near_full_scale_dbfs=-90, max_seconds=1.25, max_runs=1
        ),
    )
    measurement = report.tracks[0].audio[0]
    assert measurement.channels[1].near_full_scale_frames == 60_000
    assert len(measurement.channels[0].runs) == 1
    assert measurement.channels[0].omitted_runs == 1


def test_unreadable_audio_does_not_hide_metadata(session: Path) -> None:
    (session / 'take.wav').rename(session / 'moved.wav')
    report = session_quality.inspect(session, audio_quality.AnalysisSettings())
    assert report.tracks[0].captured_frames == 72_000
    assert any(f.kind == 'input_overflow' for f in report.findings)
    assert any(
        f.kind == 'audio_analysis_failed' and f.severity == 'error'
        for f in report.findings
    )


def test_run_stops_at_analysis_limit(session: Path) -> None:
    report = session_quality.inspect(
        session, audio_quality.AnalysisSettings(max_seconds=1)
    )
    measurement = report.tracks[0].audio[0]
    assert measurement.analyzed_frames == 48_000
    assert measurement.channels[0].runs[-1].asset_end_frame == 60_000
    assert measurement.channels[0].near_full_scale_frames == 4


@pytest.mark.parametrize('problem', ['rate', 'channels', 'nonfinite'])
def test_invalid_audio_is_an_error(session: Path, problem: str) -> None:
    data = np.zeros((96_000, 1 if problem == 'channels' else 2))
    if problem == 'nonfinite':
        data[12_000, 0] = np.nan
    if problem == 'rate':
        path = session / 'recording.toml'
        document = read_recording(path).model_copy(
            update={
                'timebases': [Timebase(name='mic-clock', rate=Rate(numerator=96_000))],
            }
        )
        path.write_text(score_toml(document))
    soundfile.write(
        session / 'take.wav',
        data,
        48_000,
        subtype='FLOAT',
    )
    report = session_quality.inspect(session, audio_quality.AnalysisSettings())
    assert report.tracks[0].audio == []
    assert any(f.kind == 'audio_analysis_failed' for f in report.findings)


def test_cli_text_and_json_agree_and_advisories_do_not_fail(
    session: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = [str(session), '--analyze-audio', '--analysis.max-seconds', '1.25']
    assert session_quality.main([*arguments, '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert session_quality.main(arguments) == 0
    text = capsys.readouterr().out
    for finding in report['findings']:
        assert f'{finding["severity"].upper()} {finding["kind"]}:' in text
        assert finding['evidence'] in text


def test_unreadable_document_fails_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert session_quality.main([str(tmp_path), '--json']) == 1
    assert 'unreadable_recording' in capsys.readouterr().out
