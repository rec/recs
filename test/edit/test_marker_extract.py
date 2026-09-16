import json
from pathlib import Path

import numpy as np
import pytest
import soundfile
from pytest_regressions.data_regression import DataRegressionFixture
from ufor import recording
from ufor.codec import score_toml
from ufor.streams import AudioType
from ufor.time import Rate, Timebase

from recs.base.errors import RecsError
from recs.edit import marker_extract
from recs.recording import markers, session_record
from recs.recording.files import sealed_asset
from recs.recording.read import read_recording


@pytest.fixture
def record(tmp_path: Path) -> Path:
    root = tmp_path / 'original'
    root.mkdir()
    audio = np.linspace(-0.5, 0.5, 96_000, dtype=np.float32)[:, None]
    soundfile.write(root / 'take.wav', audio, 48_000, subtype='FLOAT')
    writer = session_record.SessionRecordWriter(
        root / 'session-record.jsonl', started_at='start'
    )
    for frame in (12_000, 60_000):
        writer.write(
            session_record.EventRecord(
                type='mark',
                timestamp='marked',
                label='solo',
                positions=[
                    session_record.MarkerPosition(
                        source='Mic',
                        clock_id='mic-clock',
                        frame=frame,
                        sample_rate=48_000,
                        observed_at='observed',
                    ),
                ],
            )
        )
    writer.write(
        session_record.EventRecord(type='mark', timestamp='old', label='legacy')
    )
    writer.write(session_record.SessionFooter(ended_at='end', duration_seconds=2))
    writer.close()
    streams = [
        recording.AudioStream(
            name='mic',
            source_id='Mic',
            track_name='Voice',
            stream=AudioType(timebase='mic-clock', channels=['mono']),
            end=96_000,
            fragments=[recording.AudioFragment(asset='audio', start=0, count=96_000)],
        )
    ]
    document = recording.RecordingScore(
        name='original',
        title='Original',
        timebases=[Timebase(name='mic-clock', rate=Rate(numerator=48_000))],
        assets=[
            sealed_asset(root / 'take.wav', root, 'audio', 'wav'),
            sealed_asset(writer.path, root, 'journal', 'recs-session-v4'),
        ],
        outputs=recording.stream_outputs(streams),
        body=recording.Recording(
            state='sealed',
            started_at='start',
            ended_at='end',
            journal='journal',
            streams=streams,
        ),
    )
    path = root / 'recording.toml'
    path.write_text(score_toml(document))
    return path


def test_marker_numbers_disambiguate_repeated_labels(
    record: Path, data_regression: DataRegressionFixture
) -> None:
    values = markers.read_markers(record, read_recording(record))
    data_regression.check({'markers': [m.model_dump(mode='json') for m in values]})
    plan, edit = marker_extract.plan_extraction(
        marker_extract.ExtractCli(
            path=record, clock='mic-clock', start_marker=1, end_marker=2
        )
    )
    assert plan.start_frame == 12_000
    assert plan.end_frame == 60_000
    assert edit.body.clips[0].source_start == 12_000
    assert edit.body.clips[0].source_end == 60_000


@pytest.mark.parametrize('gap', [False, True])
def test_extract_renders_exact_samples_and_keeps_originals(
    record: Path,
    tmp_path: Path,
    gap: bool,
) -> None:
    if gap:
        document = read_recording(record)
        stream = document.body.streams[0].model_copy(
            update={
                'fragments': [
                    recording.AudioFragment(asset='audio', start=0, count=24_000),
                    recording.AudioFragment(
                        asset='audio', start=36_000, asset_start=36_000, count=60_000
                    ),
                ],
                'gaps': [
                    recording.Gap(
                        start=24_000,
                        end=36_000,
                        reason=recording.GapReason.input_overflow,
                    )
                ],
            }
        )
        record.write_text(
            score_toml(
                document.model_copy(
                    update={
                        'body': document.body.model_copy(update={'streams': [stream]}),
                    }
                )
            )
        )
    before = {p.name: p.read_bytes() for p in record.parent.iterdir()}
    destination = tmp_path / 'extracted'
    marker_extract.main(
        [
            str(record),
            '--clock',
            'mic-clock',
            '--start-marker',
            '1',
            '--end-marker',
            '2',
            '--destination',
            str(destination),
        ]
    )
    result, rate = soundfile.read(
        destination / 'audio/mic.wav', dtype='float32', always_2d=True
    )
    original, _ = soundfile.read(
        record.parent / 'take.wav', dtype='float32', always_2d=True
    )
    assert rate == 48_000
    expected = original[12_000:60_000].copy()
    if gap:
        expected[12_000:24_000] = 0
    np.testing.assert_array_equal(result, expected)
    assert (destination / 'edit.toml').is_file()
    assert (destination / 'recording.toml').is_file()
    journal = session_record.read(destination / 'session-record.jsonl')
    event = next(e for e in journal.events if e.type == 'edit_started')
    assert event.metadata['provenance']['marker_extraction']['start_frame'] == 12_000
    assert {p.name: p.read_bytes() for p in record.parent.iterdir()} == before


def test_preview_trims_lead_and_tail_without_writing(
    record: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = {p.name: p.read_bytes() for p in record.parent.iterdir()}
    marker_extract.main(
        [
            str(record),
            '--clock',
            'mic-clock',
            '--start-marker',
            '1',
            '--lead',
            '1',
            '--tail',
            '3',
            '--json',
        ]
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan['requested_start_frame'] == -36_000
    assert plan['requested_end_frame'] == 156_000
    assert plan['start_frame'] == 0
    assert plan['end_frame'] == 96_000
    assert {p.name: p.read_bytes() for p in record.parent.iterdir()} == before


@pytest.mark.parametrize(
    'options, message',
    [
        ({'start_marker': 3}, 'explicit alignment'),
        ({'start_marker': 4}, 'does not exist'),
        ({'clock': 'other-clock'}, 'explicit alignment'),
        ({'start_marker': 2, 'end_marker': 1}, 'precedes'),
        ({'end_marker': None}, 'empty'),
        ({'tracks': ['missing']}, 'chosen audio clock'),
    ],
)
def test_invalid_marker_selection_is_rejected(
    record: Path, options: dict[str, object], message: str
) -> None:
    config = marker_extract.ExtractCli.model_validate(
        dict(path=record, clock='mic-clock', start_marker=1, end_marker=2) | options
    )
    with pytest.raises(RecsError, match=message):
        marker_extract.plan_extraction(config)


def test_marker_journal_must_match_document(record: Path) -> None:
    with (record.parent / 'session-record.jsonl').open('a') as output:
        output.write('\n')
    with pytest.raises(RecsError, match='journal bytes disagree'):
        markers.read_markers(record, read_recording(record))


def test_destination_cannot_modify_original_session(record: Path) -> None:
    with pytest.raises(RecsError, match='outside the original'):
        marker_extract.main(
            [
                str(record),
                '--clock',
                'mic-clock',
                '--start-marker',
                '1',
                '--end-marker',
                '2',
                '--destination',
                str(record.parent / 'nested'),
            ]
        )
    assert not (record.parent / 'nested').exists()
