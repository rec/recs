import pytest
from pydantic import ValidationError

from recs.model.assets import Asset
from recs.model.codec import document_toml, parse_document
from recs.model.recording import (
    AudioFragment,
    AudioStream,
    Gap,
    Recording,
    RecordingDocument,
)
from recs.model.streams import AudioType
from recs.model.time import Rate, Timebase


def recording() -> RecordingDocument:
    return RecordingDocument(
        id='session',
        name='Session',
        assets=[
            Asset(id=i, path=f'{i}.wav', encoding='wav', byte_length=1, sha256='0' * 64)
            for i in ('journal', 'take')
        ],
        timebases=[Timebase(id='audio', rate=Rate(numerator=48000))],
        body=Recording(
            state='sealed',
            started_at='2026-09-04T12:00:00Z',
            ended_at='2026-09-04T12:00:03Z',
            journal='journal',
            streams=[
                AudioStream(
                    id='desk',
                    source_id='audio:desk',
                    end=144000,
                    stream=AudioType(timebase='audio', channels=['left']),
                    fragments=[AudioFragment(asset='take', start=48000, count=48000)],
                    gaps=[
                        Gap(start=0, end=48000, reason='unknown'),
                        Gap(start=96000, end=144000, reason='input_overflow'),
                    ],
                )
            ],
        ),
    )


def test_recording_round_trip_preserves_gaps_and_native_counts() -> None:
    value = recording()
    assert parse_document(document_toml(value)) == value
    stream = value.body.streams[0]
    assert isinstance(stream, AudioStream)
    assert stream.end == 144000
    assert sum(f.count for f in stream.fragments) == 48000


def test_recording_rejects_unknown_assets() -> None:
    data = recording().model_dump()
    data['assets'] = data['assets'][:1]
    with pytest.raises(ValidationError, match='unknown asset'):
        RecordingDocument.model_validate(data)


def test_gap_cannot_cover_recorded_audio() -> None:
    stream = recording().body.streams[0]
    data = stream.model_dump()
    data['gaps'] = [{'start': 0, 'end': 96000, 'reason': 'unknown'}]
    with pytest.raises(ValidationError, match='overlaps'):
        AudioStream.model_validate(data)
