"""Launch the recording command under Python's external sampling profiler."""

import os
import sys
from importlib.util import find_spec
from pathlib import Path
from tempfile import mkdtemp

from recs.base.errors import RecsError

from .cfg import Cfg
from .profile_devices import FAKE_DEVICES_ENV

ACTIVE_ENV = 'RECS_TACHYON_ACTIVE'


def launch(cfg: Cfg) -> None:
    if not (
        cfg.general.profile or cfg.general.profile_fake is not None
    ) or os.environ.get(ACTIVE_ENV):
        return
    if sys.version_info[:2] != (3, 15) or find_spec('profiling.sampling') is None:
        raise RecsError(
            'Profiling requires Python 3.15: use uv run --python 3.15 recs '
            '--profile or --profile-fake=18:10'
        )
    output = Path(mkdtemp(prefix='recs-profile-', dir=Path.cwd()))
    env = os.environ | {ACTIVE_ENV: '1'}
    if cfg.general.profile_fake is not None:
        env[FAKE_DEVICES_ENV] = cfg.general.profile_fake
    else:
        env.pop(FAKE_DEVICES_ENV, None)
    print(f'Tachyon profiles: {output}', file=sys.stderr, flush=True)
    command = [
        sys.executable,
        '-m',
        'profiling.sampling',
        'run',
        '--subprocesses',
        '--all-threads',
        '--flamegraph',
        '-o',
        str(output / 'profile.html'),
        '-m',
        'recs',
        *sys.argv[1:],
    ]
    os.execve(sys.executable, command, env)
