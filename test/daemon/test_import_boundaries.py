import json
import subprocess
import sys


def test_service_control_imports_do_not_load_recorder_audio_or_devices() -> None:
    code = """
import importlib
import json
import sys

for module in [
    'recs.daemon.cli',
    'recs.daemon.controllers',
    'recs.daemon.paths',
    'recs.daemon.renderers',
]:
    importlib.import_module(module)

def _forbidden(module, forbidden):
    return module == 'sounddevice' or module.startswith(forbidden)

forbidden = (
    'recs.audio',
    'recs.cfg.device',
    'recs.ui.recorder',
    'recs.ui.source_process',
    'recs.ui.source_recorder',
    'sounddevice',
)
loaded = sorted(module for module in sys.modules if _forbidden(module, forbidden))
print(json.dumps(loaded))
raise SystemExit(1 if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, '-c', code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == []
    assert result.returncode == 0
