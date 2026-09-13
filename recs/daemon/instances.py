import os
import time
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
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


def _directory_name(identity: InstanceIdentity) -> str:
    return f'{identity.pid}-{identity.start_token}'
