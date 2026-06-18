import importlib
import json
import subprocess as sp

import tomli


def test_console_script_entry_point() -> None:
    project = tomli.loads(open('pyproject.toml').read())['project']
    module_name, function_name = project['scripts']['recs'].split(':')

    module = importlib.import_module(module_name)

    assert callable(getattr(module, function_name))


def test_info():
    cmd = 'python -m recs --info'
    r = sp.run(cmd, text=True, check=True, stdout=sp.PIPE, shell=True).stdout
    json.loads(r)
