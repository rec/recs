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


class Selector(BaseModel):
    daemon: bool = False
    instance: int | None = None

    model_config = ConfigDict(frozen=True)


class Target(BaseModel):
    control_endpoint: str
    event_endpoint: str
    identity: InstanceIdentity | None = None

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


def selector_arguments(arguments: list[str]) -> tuple[Selector, list[str]]:
    daemon = False
    instance: int | None = None
    remaining: list[str] = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == '--daemon':
            if daemon:
                raise ValueError('--daemon may only be specified once')
            daemon = True
        elif argument == '--instance':
            if instance is not None or index + 1 == len(arguments):
                raise ValueError('--instance requires exactly one PID or position')
            index += 1
            instance = _instance_selector(arguments[index])
        elif argument.startswith('--instance='):
            if instance is not None:
                raise ValueError('--instance requires exactly one PID or position')
            instance = _instance_selector(argument.split('=', 1)[1])
        else:
            remaining.append(argument)
        index += 1
    if daemon and instance is not None:
        raise ValueError('--daemon and --instance cannot be used together')
    return Selector(daemon=daemon, instance=instance), remaining


def resolve(selector: Selector) -> Target:
    if selector.daemon:
        return Target(
            control_endpoint=str(external_control_endpoint()),
            event_endpoint=str(external_event_endpoint()),
        )
    descriptors = discover()
    if selector.instance is None:
        if local := next(
            (
                descriptor
                for descriptor in descriptors
                if descriptor.identity.role == 'local'
            ),
            None,
        ):
            return _target(local)
        return Target(
            control_endpoint=str(external_control_endpoint()),
            event_endpoint=str(external_event_endpoint()),
        )
    if selector.instance > 0:
        if selected := next(
            (
                descriptor
                for descriptor in descriptors
                if descriptor.identity.pid == selector.instance
            ),
            None,
        ):
            return _target(selected)
        raise ValueError(_unavailable_instance(selector.instance, descriptors))
    local = [
        descriptor for descriptor in descriptors if descriptor.identity.role == 'local'
    ]
    position = -selector.instance
    if position <= len(local):
        return _target(local[position - 1])
    raise ValueError(_unavailable_instance(selector.instance, descriptors))


def list_instances() -> list[dict[str, object]]:
    descriptors = discover()
    default = next(
        (
            descriptor
            for descriptor in descriptors
            if descriptor.identity.role == 'local'
        ),
        next(
            (
                descriptor
                for descriptor in descriptors
                if descriptor.identity.role == 'daemon'
            ),
            None,
        ),
    )
    return [
        {
            'pid': descriptor.identity.pid,
            'role': descriptor.identity.role,
            'profile': descriptor.identity.profile,
            'started_at': descriptor.identity.started_at,
            'sources': descriptor.sources,
            'default': descriptor == default,
        }
        for descriptor in descriptors
    ]


def settings_writer(path: str) -> InstanceDescriptor | None:
    return next(
        (descriptor for descriptor in discover() if descriptor.settings_path == path),
        None,
    )


def external_control_endpoint() -> Path | str:
    from . import paths

    return paths.external_control_endpoint()


def external_event_endpoint() -> Path | str:
    from . import paths

    return paths.external_event_endpoint()


def _instance_selector(value: str) -> int:
    try:
        instance = int(value)
    except ValueError:
        raise ValueError('--instance must be a PID or negative position') from None
    if instance == 0:
        raise ValueError('--instance cannot be zero')
    return instance


def _target(descriptor: InstanceDescriptor) -> Target:
    return Target(
        control_endpoint=descriptor.control_endpoint,
        event_endpoint=descriptor.event_endpoint,
        identity=descriptor.identity,
    )


def _unavailable_instance(
    selector: int,
    descriptors: list[InstanceDescriptor],
) -> str:
    if descriptors:
        available = ', '.join(
            f'{descriptor.identity.role} PID {descriptor.identity.pid}'
            for descriptor in descriptors
        )
    else:
        available = 'none'
    return f'Recs instance {selector} is unavailable. Live instances: {available}'


def _directory_name(identity: InstanceIdentity) -> str:
    return f'{identity.pid}-{identity.start_token}'
