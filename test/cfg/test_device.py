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


def test_query_device_does_not_receive_terminal_interrupts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kwargs: dict[str, t.Any] = {}

    def run(*args: t.Any, **run_kwargs: t.Any) -> sp.CompletedProcess[str]:
        kwargs.update(run_kwargs)
        return sp.CompletedProcess(args, 0, stdout='[]')

    monkeypatch.setattr(sp, 'run', run)

    assert device.query_devices() == []
    assert kwargs['start_new_session'] is True
