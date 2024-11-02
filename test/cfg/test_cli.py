import json
import subprocess as sp


def test_info():
    cmd = 'python -m recs --info'.split()
    try:
        r = sp.run(cmd, text=True, check=True, stdout=sp.PIPE).stdout
    except sp.CalledProcessError:
        # On Windows, Python installation can also be via the Windows store
        # When installed in this way, the python.exe acts as a "launcher" for the Python interpreter
        # It may not behave like a standalone executable, which can lead to issues
        # Especially when invoking subprocess commands.
        # A safety check is to ask the subprocess to run in a shell
        # This is an "except" case because not all Python installations are via Windows store
        # And it'll be more overhead unless absolutely necessary
        r = sp.run(cmd, text=True, check=True, stdout=sp.PIPE, shell=True).stdout
    finally:
        json.loads(r)
