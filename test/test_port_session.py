import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'scripts/port-session.py'


def test_ports_version_4_session_records_recursively(tmp_path: Path) -> None:
    session = tmp_path / 'nested' / 'session'
    session.mkdir(parents=True)
    record = session / 'session-record.jsonl'
    record.write_text(
        '{"type":"header","version":4,"started_at":"start"}\n'
        '{"type":"file_started","media_type":"audio","timestamp":"recorded",'
        '"stream_id":"audio:Mic:1","format":"wav","path":"audio/take.wav",'
        '"source":"Mic","track_name":"1","clock_id":"mic-clock",'
        '"source_channels":[1],"channels":1,"sample_rate":48000}\n'
    )

    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], check=True)

    assert [json.loads(line) for line in record.read_text().splitlines()] == [
        {'type': 'header', 'version': 5, 'started_at': 'start'},
        {
            'type': 'source_online',
            'timestamp': 'recorded',
            'source': 'Mic',
            'clock_id': 'mic-clock',
            'sample_rate': 48000,
        },
        {
            'type': 'file_started',
            'timestamp': 'recorded',
            'stream_id': 'audio:Mic:1',
            'path': 'audio/take.wav',
            'clock_id': 'mic-clock',
            'source_channels': [1],
        },
    ]

    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], check=True)

    assert len(record.read_text().splitlines()) == 3


def test_ports_headerless_version_4_session_records(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"file_started","media_type":"audio","timestamp":"recorded",'
        '"stream_id":"audio:Mic:1","format":"wav","path":"audio/take.wav",'
        '"source":"Mic","track_name":"1","clock_id":"mic-clock",'
        '"source_channels":[1],"channels":1,"sample_rate":48000}\n'
    )

    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], check=True)

    assert [json.loads(line) for line in record.read_text().splitlines()] == [
        {'type': 'header', 'version': 5, 'started_at': 'recorded'},
        {
            'type': 'source_online',
            'timestamp': 'recorded',
            'source': 'Mic',
            'clock_id': 'mic-clock',
            'sample_rate': 48000,
        },
        {
            'type': 'file_started',
            'timestamp': 'recorded',
            'stream_id': 'audio:Mic:1',
            'path': 'audio/take.wav',
            'clock_id': 'mic-clock',
            'source_channels': [1],
        },
    ]


def test_ports_audio_records_without_clock_ids(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"file_started","media_type":"audio","timestamp":"recorded",'
        '"stream_id":"audio:Mic:1","format":"wav","path":"audio/take.wav",'
        '"source":"Mic","track_name":"1","source_channels":[1],'
        '"channels":1,"sample_rate":48000}\n'
    )

    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], check=True)

    records = [json.loads(line) for line in record.read_text().splitlines()]
    assert records[1]['clock_id'] == 'clock-1f0ebc6982b6c2d2'
    assert records[2]['clock_id'] == 'clock-1f0ebc6982b6c2d2'


def test_ports_audio_finish_without_source_name(tmp_path: Path) -> None:
    record = tmp_path / 'session-record.jsonl'
    record.write_text(
        '{"type":"file_finished","media_type":"audio","timestamp":"recorded",'
        '"stream_id":"audio:FLOW 8:1-2","format":"wav","path":"audio/take.wav",'
        '"track_name":"1-2","source_channels":[1,2],"channels":2,'
        '"sample_rate":48000,"quantity_count":1}\n'
    )

    subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], check=True)

    records = [json.loads(line) for line in record.read_text().splitlines()]
    assert records[1]['source'] == 'FLOW 8'
