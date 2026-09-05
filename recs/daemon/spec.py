from pathlib import Path

from reccy.services import spec

RECS_SERVICE = spec.load(Path(__file__).with_name('service.toml'))
