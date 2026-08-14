from pathlib import Path

PROBLEMATIC = r'\/:*?"<>|'
REPLACEMENTS = str.maketrans(PROBLEMATIC, '-' * len(PROBLEMATIC))


def legal_filename(s: str) -> str:
    return s.translate(REPLACEMENTS)


def legal_path(path: Path) -> Path:
    return Path(
        *(part if part == path.anchor else legal_filename(part) for part in path.parts)
    )
