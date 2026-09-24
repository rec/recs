import hashlib
import json
import sys
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import tyro
from pydantic import BaseModel


class Arguments(BaseModel, frozen=True):
    directory: Annotated[Path, tyro.conf.Positional]


def capture_clock_id(source: str) -> str:
    return 'clock-' + hashlib.sha256(source.encode()).hexdigest()[:16]


def audio_fields(record: dict[str, object]) -> tuple[str, str, str, int]:
    stream_id = record.get('stream_id')
    clock_id = record.get('clock_id')
    sample_rate = record.get('sample_rate')
    if not isinstance(stream_id, str):
        raise ValueError(f'Audio record has no stream ID: {record!r}')
    if not isinstance(sample_rate, int):
        raise ValueError(f'Audio record has no sample rate: {record!r}')
    source = record.get('source')
    track_name = record.get('track_name')
    if (
        not isinstance(source, str)
        and isinstance(track_name, str)
        and stream_id.startswith('audio:')
        and stream_id.endswith(f':{track_name}')
    ):
        source = stream_id.removeprefix('audio:').removesuffix(f':{track_name}')
    if not isinstance(source, str) or not isinstance(track_name, str):
        raise ValueError(f'Audio record has no source or track name: {record!r}')
    if not isinstance(clock_id, str):
        clock_id = capture_clock_id(source)
    return source, track_name, clock_id, sample_rate


def audio_stream_id(source: str, track_name: str) -> str:
    return f'audio:{quote(source, safe="-_.~")}:{quote(track_name, safe="-_.~")}'


def port(path: Path) -> bool:
    records = [json.loads(line) for line in path.read_text().splitlines() if line]
    if not records or not all(isinstance(record, dict) for record in records):
        raise ValueError('has no JSON object records')
    if records[0].get('type') == 'header':
        version = records[0].get('version')
        if version == 5:
            return False
        if version != 4:
            raise ValueError(f'has unsupported session version: {version!r}')
    else:
        first_audio = next(
            (
                record
                for record in records
                if isinstance(record.get('stream_id'), str)
                and record['stream_id'].startswith('audio:')
                and record.get('media_type') == 'audio'
            ),
            None,
        )
        if first_audio is None or not isinstance(
            timestamp := first_audio.get('timestamp'), str
        ):
            raise ValueError('has no version 4 header or audio records')
        records.insert(0, {'type': 'header', 'version': 4, 'started_at': timestamp})

    clocks: dict[str, tuple[str, int]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f'{path} has a non-object record')
        stream_id = record.get('stream_id')
        if not isinstance(stream_id, str) or not stream_id.startswith('audio:'):
            continue
        source, track_name, clock_id, sample_rate = audio_fields(record)
        if previous := clocks.get(clock_id):
            if previous != (source, sample_rate):
                raise ValueError(f'{path} has inconsistent device evidence: {clock_id}')
        else:
            clocks[clock_id] = (source, sample_rate)
        record['stream_id'] = audio_stream_id(source, track_name)
        record['clock_id'] = clock_id
        for field in (
            'media_type',
            'format',
            'source',
            'track_name',
            'channels',
            'sample_rate',
        ):
            record.pop(field, None)

    records[0]['version'] = 5
    online: set[str] = set()
    ported: list[dict[str, object]] = []
    for record in records:
        stream_id = record.get('stream_id')
        clock_id = record.get('clock_id')
        if (
            isinstance(stream_id, str)
            and stream_id.startswith('audio:')
            and isinstance(clock_id, str)
            and clock_id not in online
        ):
            source, sample_rate = clocks[clock_id]
            timestamp = record.get('timestamp')
            if not isinstance(timestamp, str):
                raise ValueError(f'{path} has audio without a timestamp: {record!r}')
            ported.append(
                {
                    'type': 'source_online',
                    'timestamp': timestamp,
                    'source': source,
                    'clock_id': clock_id,
                    'sample_rate': sample_rate,
                }
            )
            online.add(clock_id)
        ported.append(record)
    path.write_text(
        ''.join(json.dumps(record, separators=(',', ':')) + '\n' for record in ported)
    )
    return True


def main(arguments: Arguments) -> None:
    for path in sorted(arguments.directory.rglob('session-record.jsonl')):
        try:
            if port(path):
                print(path)
        except (json.JSONDecodeError, ValueError) as error:
            print(f'Skipped {path}: {error}', file=sys.stderr)


if __name__ == '__main__':
    main(tyro.cli(Arguments))
