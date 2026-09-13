import os
import time
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from reccy.configuration import settings
from reccy.protocol import rpc
from reccy.services import models

InstanceRole = Literal['daemon', 'local']


class InstanceIdentity(BaseModel):
    pid: int = Field(gt=0)
    start_token: str = Field(min_length=1)
    started_at: int = Field(gt=0)
    role: InstanceRole
    profile: str | None = None

    model_config = ConfigDict(frozen=True)


class InstanceDescriptor(BaseModel):
    identity: InstanceIdentity
    control_endpoint: str
    event_endpoint: str
    protocol_version: int
    sources: list[str] = Field(default_factory=list)
    settings_path: str | None = None

    model_config = ConfigDict(frozen=True)


def new_identity(role: InstanceRole, profile: str | None = None) -> InstanceIdentity:
    return InstanceIdentity(
        pid=os.getpid(),
        start_token=uuid.uuid4().hex,
        started_at=time.time_ns(),
        role=role,
        profile=profile,
    )


def instances_directory(
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> Path:
    root = home or Path.home()
    if platform == models.Platform.windows:
        return root / 'AppData/Local/recs/instances'
    return root / '.local/state/recs/instances'


def local_control_endpoint(
    identity: InstanceIdentity,
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> Path | str:
    if platform == models.Platform.windows:
        return rf'\\.\pipe\recs-{identity.pid}-{identity.start_token}-control'
    return (
        instances_directory(home, platform) / _directory_name(identity) / 'control.sock'
    )


def local_event_endpoint(
    identity: InstanceIdentity,
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> Path | str:
    if platform == models.Platform.windows:
        return rf'\\.\pipe\recs-{identity.pid}-{identity.start_token}-events'
    return (
        instances_directory(home, platform) / _directory_name(identity) / 'events.sock'
    )


def descriptor_path(
    identity: InstanceIdentity,
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> Path:
    return instances_directory(home, platform) / f'{_directory_name(identity)}.json'


def publish(
    descriptor: InstanceDescriptor,
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> Path:
    path = descriptor_path(descriptor.identity, home, platform)
    settings.write_json_model(path, descriptor, indent=2)
    return path


def remove(
    identity: InstanceIdentity,
    home: Path | None = None,
    platform: models.Platform | None = None,
) -> None:
    descriptor_path(identity, home, platform).unlink(missing_ok=True)


def discover(
    home: Path | None = None,
    platform: models.Platform | None = None,
    client: type[rpc.Client] = rpc.Client,
) -> list[InstanceDescriptor]:
    descriptors: list[InstanceDescriptor] = []
    for path in instances_directory(home, platform).glob('*.json'):
        try:
            descriptor = InstanceDescriptor.model_validate_json(path.read_text())
            response = client(
                descriptor.control_endpoint,
                role='recs-discovery',
                timeout=1,
            ).call('capabilities')
            if not isinstance(response, dict):
                continue
            identity = InstanceIdentity.model_validate(response.get('instance'))
        except (OSError, TimeoutError, ValueError):
            continue
        if identity == descriptor.identity:
            descriptors.append(descriptor)
    return sorted(
        descriptors,
        key=lambda descriptor: (
            descriptor.identity.started_at,
            descriptor.identity.pid,
            descriptor.identity.start_token,
        ),
        reverse=True,
    )


def _directory_name(identity: InstanceIdentity) -> str:
    return f'{identity.pid}-{identity.start_token}'
