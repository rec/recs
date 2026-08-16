from pathlib import Path

from reccy import service_spec

RECS_SERVICE = service_spec.load(Path(__file__).with_name('service.toml'))
