import pytest
from pydantic import ValidationError

from recs.model.assets import Asset


@pytest.mark.parametrize('path', ['../a.wav', '/a.wav', 'C:/a.wav', 'https://x/a', '.'])
def test_assets_require_contained_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        Asset(id='take', path=path, encoding='wav', byte_length=0, sha256='0' * 64)


def test_asset_identity_round_trips() -> None:
    asset = Asset(
        id='take',
        path='audio/take.wav',
        encoding='wav',
        byte_length=44,
        sha256='a' * 64,
    )
    assert Asset.model_validate_json(asset.model_dump_json()) == asset
