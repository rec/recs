import pytest

from recs.base import RecsError
from recs.daemon import root_user


def test_is_root_uses_effective_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(root_user.os, 'geteuid', lambda: 0)

    assert root_user.is_root()


def test_is_root_is_false_without_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(root_user.os, 'geteuid', raising=False)
    monkeypatch.delattr(root_user.os, 'getuid', raising=False)

    assert not root_user.is_root()


def test_raise_if_root_uses_daemon_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(root_user, 'is_root', lambda: True)

    with pytest.raises(RecsError, match=root_user.ROOT_DAEMON_ERROR):
        root_user.raise_if_root()
