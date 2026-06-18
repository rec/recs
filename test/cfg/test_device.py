import subprocess as sp
import typing as t

import pytest

from recs.cfg import device


def test_input_devices():
    if d := device.input_devices():
        print(next(iter(d.values())))


def test_query_device_failure_is_not_an_empty_device_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = sp.CalledProcessError(1, device.CMD)

    def fail(*args: t.Any, **kwargs: t.Any) -> t.NoReturn:
        raise error

    monkeypatch.setattr(sp, 'run', fail)

    with pytest.raises(sp.CalledProcessError) as exc_info:
        device.query_devices()

    assert exc_info.value is error
