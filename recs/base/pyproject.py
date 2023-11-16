from pathlib import Path

import tomli

PYPROJECT = Path(__file__).parents[2] / 'pyproject.toml'
assert PYPROJECT.exists()


def message() -> str:
    p = tomli.loads(PYPROJECT.read_text())['tool']['poetry']
    desc, name = p['description'], p['name']

    icon, *d, icon2 = desc.split()
    assert icon == icon2 and d
    desc = ' '.join(d)
    return f'{icon} {name}: {desc} {icon}'
