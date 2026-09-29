"""Resolve finite uFor assets under explicit recs host authority."""

from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from reccy.runtime.assets import (
    AssetCacheError,
    AssetCacheMiss,
    AssetStore,
    MediaKind,
    ObjectIdentity,
    SourceKind,
    source_fingerprint,
)
from reccy.runtime.file_assets import VolumeMount, open_file_asset, resolve_volume_root
from reccy.runtime.git_assets import import_remote_git_file
from reccy.runtime.http_assets import AssetAcquisitionDenied, open_https_asset
from ufor.assets import (
    Asset,
    DownloadLocation,
    GitFileLocation,
    RelativeFileLocation,
    VolumeFileLocation,
)


class FiniteAssetResolver:
    """Open verified bytes; the caller must keep this context open while reading.

    ``store`` and the bare Git transport repository belong to one credential
    scope. The host supplies measured mounts and exact approved remote URLs.
    No score declaration grants acquisition authority by itself.
    """

    def __init__(
        self,
        store: AssetStore,
        *,
        mounts: list[VolumeMount],
        approved_https_urls: list[str],
        https_headers: Mapping[str, str] | None,
        approved_git_urls: list[str],
        git_transport_repository: Path | None,
        fingerprint_key: bytes,
        maximum_bytes: int,
        timeout: float,
    ) -> None:
        if len(fingerprint_key) < 32:
            raise ValueError('fingerprint_key must contain at least 32 bytes')
        self.store = store
        self.mounts = mounts
        self.approved_https_urls = approved_https_urls
        self.https_headers = https_headers
        self.approved_git_urls = approved_git_urls
        self.git_transport_repository = git_transport_repository
        self.fingerprint_key = fingerprint_key
        self.maximum_bytes = maximum_bytes
        self.timeout = timeout

    @contextmanager
    def open(
        self, asset: Asset, package_root: Path, *, trusted_immutable: bool = False
    ) -> Iterator[BinaryIO]:
        """Authorize, acquire, and verify one finite asset for this use."""
        if asset.content is None:
            raise AssetCacheError(f'Asset is not a finite byte source: {asset.name}')
        expected = ObjectIdentity(
            sha256=asset.content.sha256, length=asset.content.byte_length
        )
        location = asset.location
        context: dict[str, object]
        if isinstance(location, RelativeFileLocation):
            root = package_root
            source_kind = SourceKind.local_file
            context = {'package_root': str(root.resolve())}
        elif isinstance(location, VolumeFileLocation):
            root = resolve_volume_root(
                location.volume_id, location.volume_name, self.mounts
            )
            source_kind = SourceKind.volume_file
            context = {'volume_id': location.volume_id}
        elif isinstance(location, DownloadLocation):
            with open_https_asset(
                self.store,
                location.url,
                expected,
                allow_url=lambda url: url in self.approved_https_urls,
                fingerprint_key=self.fingerprint_key,
                maximum_encoded_bytes=self.maximum_bytes,
                maximum_decoded_bytes=self.maximum_bytes,
                timeout=self.timeout,
                headers=self.https_headers,
                media_kind=MediaKind.other,
            ) as file:
                yield file
            return
        elif isinstance(location, GitFileLocation):
            if location.repository not in self.approved_git_urls:
                raise AssetAcquisitionDenied('Host policy denied the Git repository')
            if urlsplit(location.repository).scheme not in {'git', 'https', 'ssh'}:
                raise AssetAcquisitionDenied('Git transport scheme is unsupported')
            with ExitStack() as stack:
                try:
                    file = stack.enter_context(self.store.open_expected(expected))
                except AssetCacheMiss:
                    pass
                else:
                    yield file
                    return
            if self.git_transport_repository is None:
                raise AssetAcquisitionDenied('Git transport storage is not configured')
            source_key = source_fingerprint(
                location.model_dump(mode='json'), {}, expected, {}
            )
            entry, _ = import_remote_git_file(
                self.store,
                location.repository,
                self.git_transport_repository,
                location.commit,
                location.path,
                expected,
                maximum_bytes=self.maximum_bytes,
                source_key=source_key,
            )
            with self.store.open_entry(entry.id) as file:
                yield file
            return
        else:
            raise AssetCacheError(f'Asset is not a finite byte source: {asset.name}')
        source_key = source_fingerprint(
            location.model_dump(mode='json'), context, expected, {}
        )
        with open_file_asset(
            self.store,
            root,
            location.path,
            expected,
            source_key=source_key,
            source_kind=source_kind,
            trusted_immutable=trusted_immutable,
            maximum_bytes=self.maximum_bytes,
        ) as file:
            yield file
