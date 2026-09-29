import hashlib
from pathlib import Path

import pytest
from reccy.runtime.assets import (
    AssetCategory,
    AssetIdentityMismatch,
    AssetStore,
    SourceKind,
    source_fingerprint,
)
from reccy.runtime.file_assets import VolumeMount, VolumeNotFound
from reccy.runtime.http_assets import AssetAcquisitionDenied
from ufor.assets import (
    Asset,
    ContentIdentity,
    DownloadLocation,
    GitFileLocation,
    RelativeFileLocation,
    VolumeFileLocation,
)

from recs.recording.asset_resolver import FiniteAssetResolver


def test_mutable_relative_asset_is_read_from_verified_snapshot(tmp_path: Path) -> None:
    package = tmp_path / 'package'
    package.mkdir()
    source = package / 'take.bin'
    source.write_bytes(b'first take')
    resolver = _resolver(tmp_path)
    asset = _asset(RelativeFileLocation(path='take.bin'), b'first take')

    with resolver.open(asset, package) as file:
        source.write_bytes(b'changed!!!')
        assert file.read() == b'first take'

    with pytest.raises(AssetIdentityMismatch):
        with resolver.open(asset, package):
            pass


def test_volume_asset_requires_matching_measured_id(tmp_path: Path) -> None:
    volume = tmp_path / 'volume'
    volume.mkdir()
    (volume / 'take.bin').write_bytes(b'volume take')
    resolver = _resolver(
        tmp_path, mounts=[VolumeMount(volume_id='volume-1', root=volume)]
    )
    asset = _asset(
        VolumeFileLocation(volume_id='volume-1', path='take.bin'), b'volume take'
    )

    with resolver.open(asset, tmp_path) as file:
        assert file.read() == b'volume take'

    wrong = asset.model_copy(
        update={'location': VolumeFileLocation(volume_id='volume-2', path='take.bin')}
    )
    with pytest.raises(VolumeNotFound):
        with resolver.open(wrong, tmp_path):
            pass


def test_cached_download_requires_authorization(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / 'cache', credential_scope='operator')
    contents = b'cached bytes'
    url = 'https://example.test/take.bin'
    asset = _asset(DownloadLocation(url=url), contents)
    store.import_bytes(
        contents,
        source_key=source_fingerprint({'kind': 'test'}, {}, None, {}),
        category=AssetCategory.acquired,
        source_kind=SourceKind.download,
    )
    denied = _resolver(tmp_path, store=store)
    with pytest.raises(AssetAcquisitionDenied):
        with denied.open(asset, tmp_path):
            pass

    allowed = _resolver(tmp_path, store=store, approved_https_urls=[url])
    with allowed.open(asset, tmp_path) as file:
        assert file.read() == contents


def test_pinned_git_asset_reuses_verified_bytes_offline(tmp_path: Path) -> None:
    store = AssetStore(tmp_path / 'cache', credential_scope='operator')
    contents = b'git bytes'
    repository = 'https://example.test/library.git'
    asset = _asset(
        GitFileLocation(repository=repository, commit='a' * 40, path='audio/take.bin'),
        contents,
    )
    store.import_bytes(
        contents,
        source_key=source_fingerprint({'kind': 'test'}, {}, None, {}),
        category=AssetCategory.acquired,
        source_kind=SourceKind.git_file,
    )
    resolver = _resolver(tmp_path, store=store, approved_git_urls=[repository])

    with resolver.open(asset, tmp_path) as file:
        assert file.read() == contents

    denied = _resolver(tmp_path, store=store)
    with pytest.raises(AssetAcquisitionDenied):
        with denied.open(asset, tmp_path):
            pass


def _asset(
    location: RelativeFileLocation
    | VolumeFileLocation
    | DownloadLocation
    | GitFileLocation,
    contents: bytes,
) -> Asset:
    return Asset.model_validate(
        {
            'name': 'take',
            'encoding': 'application/octet-stream',
            'location': location.model_dump(mode='json'),
            'content': ContentIdentity(
                byte_length=len(contents), sha256=hashlib.sha256(contents).hexdigest()
            ),
        }
    )


def _resolver(
    root: Path,
    *,
    store: AssetStore | None = None,
    mounts: list[VolumeMount] | None = None,
    approved_https_urls: list[str] | None = None,
    approved_git_urls: list[str] | None = None,
) -> FiniteAssetResolver:
    return FiniteAssetResolver(
        store or AssetStore(root / 'cache', credential_scope='operator'),
        mounts=mounts or [],
        approved_https_urls=approved_https_urls or [],
        https_headers=None,
        approved_git_urls=approved_git_urls or [],
        git_transport_repository=None,
        fingerprint_key=b'x' * 32,
        maximum_bytes=1024,
        timeout=1,
    )
