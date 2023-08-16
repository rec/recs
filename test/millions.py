from rich.console import Console
import time

CONSOLE = Console(color_system='truecolor')

def colors():
    rgb = [0, 0, 0]
    while True:
        yield (rgb := [(c + i + 2) % 256 for i, c in enumerate(rgb)])


def console():
    for r, g, b in colors():
        CONSOLE.print('hello', style=f'rgb({r},{g},{b})')
        time.sleep(0.1)


if __name__ == '__main__':
    console()
