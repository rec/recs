import re
from pathlib import Path

import tyro
from pydantic import BaseModel


class Arguments(BaseModel, frozen=True):
    dry_run: bool = False


def new_name(name: str) -> str | None:
    if match := re.fullmatch(
        r'FLOW 8 \(Recording\) \+ (\d+-\d+) \+ (\d{8}-\d{6})(\.flac|\.WAV)', name
    ):
        return f'{match[1]} + {match[2]}{match[3]}'
    if match := re.fullmatch(
        r'FLOW 8 \+ (\d+-\d+) \+ (\d{8}-\d{6})(\.flac|\.WAV)', name
    ):
        return f'{match[1]} + {match[2]}{match[3]}'
    if match := re.fullmatch(
        r'LiveTrak L-12 master \+ MASTER \+ (\d{8}-\d{6})(\.flac|\.WAV)', name
    ):
        return f'master + {match[1]}{match[2]}'
    if match := re.fullmatch(
        r'LiveTrak L-12 \+ TRACK(\d{2})_(\d{2}) \+ (\d{8}-\d{6})(\.flac|\.WAV)',
        name,
    ):
        return f'{int(match[1])}-{int(match[2])} + {match[3]}{match[4]}'
    if match := re.fullmatch(
        r'LiveTrak L-12 \+ TRACK(\d{2}) \+ (\d{8}-\d{6})(\.flac|\.WAV)', name
    ):
        return f'{int(match[1])} + {match[2]}{match[3]}'
    return None


def main(arguments: Arguments) -> None:
    renames = {
        path: path.with_name(updated)
        for path in Path('results').rglob('*')
        if path.is_file()
        and path.parent.name == 'audio'
        and (updated := new_name(path.name)) is not None
    }
    destinations = set(renames.values())
    if len(destinations) != len(renames):
        raise ValueError('multiple result files would have the same name')
    if existing := next((p for p in destinations if p.exists()), None):
        raise FileExistsError(existing)

    replacements: dict[Path, dict[str, str]] = {}
    for source, destination in renames.items():
        session = source.parent.parent
        replacements.setdefault(session, {})[f'audio/{source.name}'] = (
            f'audio/{destination.name}'
        )
        if source.suffix == '.flac':
            replacements[session][f'audio/{source.stem}.wav'] = (
                f'audio/{destination.stem}.flac'
            )
        if source.suffix == '.WAV':
            replacements[session][f'audio/{source.stem}.wav'] = (
                f'audio/{destination.stem}.WAV'
            )

    updates: dict[Path, str] = {}
    for session, paths in replacements.items():
        for name in ('recording.toml', 'session-record.jsonl'):
            path = session / name
            if path.exists():
                original = path.read_text()
                content = original
                for old, new in paths.items():
                    content = content.replace(old, new)
                if content != original:
                    updates[path] = content

    for source, destination in renames.items():
        print(f'{source} -> {destination}')
    for path in updates:
        print(path)
    for name in ('LiveTrak', 'MacBook', 'FLOW'):
        count = sum(
            name in renames.get(path, path).name
            for path in Path('results').rglob('*')
            if path.is_file()
        )
        print(f'Remaining files containing {name}: {count}')
    if arguments.dry_run:
        return

    for source, destination in renames.items():
        source.rename(destination)

    for path, content in updates.items():
        path.write_text(content)


if __name__ == '__main__':
    main(tyro.cli(Arguments))
