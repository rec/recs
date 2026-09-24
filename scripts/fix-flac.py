from pathlib import Path


def main() -> None:
    for path in Path('results').rglob('*'):
        if path.name not in {'recording.toml', 'session-record.jsonl'}:
            continue
        content = path.read_text()
        updated = content.replace('.wav', '.flac')
        if updated != content:
            path.write_text(updated)


if __name__ == '__main__':
    main()
