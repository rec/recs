"""Host authority for finite assets used by an offline command."""

import secrets
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from reccy.runtime.assets import AssetStore
from reccy.runtime.file_assets import VolumeMount

from recs.base.errors import RecsError

from .asset_resolver import FiniteAssetResolver
from .recording_paths import mounted_disk_uuid


class FiniteAssetPolicy(BaseModel, frozen=True):
    cache_root: Path
    credential_scope: str = Field(min_length=1)
    maximum_bytes: int = Field(gt=0, strict=True)
    timeout: float = Field(gt=0, allow_inf_nan=False)
    volumes: list[VolumeMount] = Field(default_factory=list)
    approved_https_urls: list[str] = Field(default_factory=list)
    approved_git_urls: list[str] = Field(default_factory=list)
    git_transport_repository: Path | None = None

    model_config = ConfigDict(extra='forbid')


def load_asset_policy(path: Path) -> FiniteAssetResolver:
    try:
        policy = FiniteAssetPolicy.model_validate(tomllib.loads(path.read_text()))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, ValidationError) as error:
        raise RecsError(f'Cannot read asset policy {path}: {error}') from error
    if not policy.cache_root.is_absolute():
        raise RecsError('Asset cache_root must be an absolute path')
    if (
        policy.git_transport_repository is not None
        and not policy.git_transport_repository.is_absolute()
    ):
        raise RecsError('Git transport repository must be an absolute path')
    for mount in policy.volumes:
        if not mount.root.is_absolute() or not mount.root.is_mount():
            raise RecsError(f'Volume root is not an absolute mount: {mount.root}')
        try:
            observed = mounted_disk_uuid(mount.root)
        except OSError as error:
            raise RecsError(f'Cannot identify volume {mount.root}: {error}') from error
        if observed != mount.volume_id:
            raise RecsError(
                f'Volume ID mismatch at {mount.root}: '
                f'expected {mount.volume_id}, observed {observed or "none"}'
            )
    return FiniteAssetResolver(
        AssetStore(policy.cache_root, credential_scope=policy.credential_scope),
        mounts=policy.volumes,
        approved_https_urls=policy.approved_https_urls,
        https_headers=None,
        approved_git_urls=policy.approved_git_urls,
        git_transport_repository=policy.git_transport_repository,
        fingerprint_key=secrets.token_bytes(32),
        maximum_bytes=policy.maximum_bytes,
        timeout=policy.timeout,
    )
