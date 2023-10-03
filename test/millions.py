import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

CONSOLE = Console(color_system='truecolor')


def colors():
    rgb = [0, 0, 0]
    while True:
        yield (rgb := [(c + i + 2) % 256 for i, c in enumerate(rgb)])


def console():
    for r, g, b in colors():
        CONSOLE.print('hello', style=f'rgb({r},{g},{b})')
        time.sleep(0.1)


def table(r=0, g=0, b=0):
    t = Table('Greetings')
    t.add_row(f'[rgb({r},{g},{b})]hello')
    return t


def live():
    with Live(table(), console=CONSOLE, auto_refresh=False) as live:
        for r, g, b in colors():
            live.update(table(r, g, b))
            live.refresh()
            time.sleep(0.05)


if __name__ == '__main__':
    live()
