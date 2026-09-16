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

from recs.base.errors import RecsError
from recs.edit import track_handoff
from recs.recording import session_record
from recs.recording.files import sealed_asset
from recs.recording.read import read_recording


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / 'original'
    root.mkdir()
    samples = np.linspace(-0.5, 0.5, 96_000, dtype=np.float32)
    audio = np.column_stack([samples, -samples])
    for name in ('a', 'b'):
        soundfile.write(root / f'{name}.wav', audio, 48_000, subtype='FLOAT')
    writer = session_record.SessionRecordWriter(
        root / 'session-record.jsonl', started_at='start'
    )
    for frame in (0, 12_000, 72_000, 84_000):
        writer.write(
            session_record.EventRecord(
                type='mark',
                timestamp='marked',
                label='marker',
                positions=[
                    session_record.MarkerPosition(
                        source='Mic',
                        clock_id='mic',
                        frame=frame,
                        sample_rate=48_000,
                        observed_at='observed',
                    )
                ],
            )
        )
    writer.write(session_record.SessionFooter(ended_at='end', duration_seconds=2))
    writer.close()
    streams = [
        recording.AudioStream(
            name='a',
            source_id='Mic',
            track_name='Voice',
            stream=AudioType(timebase='mic', channels=['left', 'right']),
            end=96_000,
            fragments=[recording.AudioFragment(asset='a', start=0, count=48_000)],
            gaps=[recording.Gap(start=48_000, end=96_000, reason='silence_suppressed')],
        ),
        recording.AudioStream(
            name='b',
            source_id='Mic',
            track_name='Room',
            stream=AudioType(timebase='mic', channels=['left', 'right']),
            end=96_000,
            fragments=[
                recording.AudioFragment(
                    asset='b', start=24_000, asset_start=24_000, count=72_000
                )
            ],
            gaps=[recording.Gap(start=0, end=24_000, reason='input_overflow')],
        ),
    ]
    document = recording.RecordingScore(
        name='capture',
        title='Capture',
        timebases=[Timebase(name='mic', rate=Rate(numerator=48_000))],
        assets=[sealed_asset(root / f'{n}.wav', root, n, 'wav') for n in ('a', 'b')]
        + [sealed_asset(writer.path, root, 'journal', 'recs-session-v4')],
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


def test_handoff_keeps_shared_origin_channels_gap_reasons_and_markers(
    source: Path, tmp_path: Path, data_regression: DataRegressionFixture
) -> None:
    before = {p: p.read_bytes() for p in source.parent.iterdir()}
    plan, edit = track_handoff.plan_handoff(
        track_handoff.HandoffCli(
            path=source,
            clock='mic',
            start_frame=12_000,
            end_frame=84_000,
            tracks=['b', 'a'],
        )
    )
    normalized = json.loads(plan.model_dump_json().replace(str(source), '<recording>'))
    data_regression.check(normalized)
    target = track_handoff.render_handoff(plan, edit, tmp_path / 'handoff')
    assert json.loads((target / 'handoff.json').read_text()) == plan.model_dump(
        mode='json'
    )
    original, _ = soundfile.read(
        source.parent / 'a.wav', dtype='float32', always_2d=True
    )
    for index, track in enumerate(plan.tracks):
        path = target / track.path
        info = soundfile.info(path)
        assert (info.frames, info.channels, info.samplerate, info.subtype) == (
            72_000,
            2,
            48_000,
            'FLOAT',
        )
        actual, _ = soundfile.read(path, dtype='float32', always_2d=True)
        expected = original[12_000:84_000].copy()
        if index == 0:
            expected[36_000:] = 0
        else:
            expected[:12_000] = 0
        np.testing.assert_array_equal(actual, expected)
    assert read_recording(target / 'recording.toml').body.state == 'sealed'
    journal = session_record.read(target / 'session-record.jsonl')
    event = next(e for e in journal.events if e.type == 'edit_started')
    assert event.metadata['provenance']['track_handoff'] == plan.model_dump(mode='json')
    assert {p: p.read_bytes() for p in source.parent.iterdir()} == before


@pytest.mark.parametrize(
    'problem', ['clock', 'rate', 'unmapped', 'interval', 'continuation']
)
def test_handoff_rejects_unsupported_placement_before_writing(
    source: Path, tmp_path: Path, problem: str
) -> None:
    document = read_recording(source)
    if problem == 'clock':
        document.timebases.append(
            Timebase(name='independent', rate=Rate(numerator=48_000))
        )
        document.body.streams[1] = document.body.streams[1].model_copy(
            update={
                'stream': AudioType(timebase='independent', channels=['left', 'right'])
            }
        )
        document = document.model_copy(
            update={'outputs': recording.stream_outputs(document.body.streams)}
        )
    elif problem == 'rate':
        document.timebases[0] = Timebase(
            name='mic', rate=Rate(numerator=96_001, denominator=2)
        )
    elif problem == 'unmapped':
        document.body.streams[0] = document.body.streams[0].model_copy(
            update={
                'fragments': [],
                'gaps': [],
                'unmapped_fragments': [
                    recording.UnmappedAudioFragment(
                        asset='a',
                        count=96_000,
                        journal_range=TickRange(start=0, end=96_000),
                    )
                ],
            }
        )
    elif problem == 'continuation':
        document = document.model_copy(
            update={
                'body': document.body.model_copy(
                    update={'continued_at': ['next/recording.toml']}
                )
            }
        )
    source.write_text(score_toml(document))
    destination = tmp_path / 'handoff'
    with pytest.raises(RecsError):
        track_handoff.main(
            [
                str(source),
                '--clock',
                'mic',
                '--start-frame',
                '12000',
                '--end-frame',
                '100000' if problem == 'interval' else '84000',
                '--tracks',
                'a',
                'b',
                '--destination',
                str(destination),
            ]
        )
    assert not destination.exists()
    assert not list(tmp_path.glob('.handoff.recs-handoff-*'))


def test_sidecar_failure_does_not_publish_bundle(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, edit = track_handoff.plan_handoff(
        track_handoff.HandoffCli(
            path=source, clock='mic', start_frame=12_000, end_frame=84_000
        )
    )
    write = Path.write_text

    def fail(path: Path, data: str, *args: object, **kwargs: object) -> int:
        if path.name == 'handoff.json':
            raise OSError('disk full')
        return write(path, data)

    monkeypatch.setattr(Path, 'write_text', fail)
    with pytest.raises(RecsError, match='Handoff not published'):
        track_handoff.render_handoff(plan, edit, tmp_path / 'handoff')
    assert not (tmp_path / 'handoff').exists()
    assert len(list(tmp_path.glob('.handoff.recs-handoff-*'))) == 1
