import json
import subprocess as sp


def test_info():
    cmd = 'python -m recs --info'.split()
    r = sp.run(cmd, text=True, check=True, stdout=sp.PIPE, shell=True).stdout
    json.loads(r)
