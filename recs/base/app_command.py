import sys


def command(*args: str) -> list[str]:
    if getattr(sys, 'frozen', False):
        return [sys.executable, *args]
    return [sys.executable, '-m', 'recs', *args]
