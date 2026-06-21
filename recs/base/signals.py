import contextlib
import signal
import threading
import types
import typing as t

TERMINATION_SIGNAL_NAMES = ('SIGHUP', 'SIGINT', 'SIGQUIT', 'SIGTERM')


@contextlib.contextmanager
def raise_keyboard_interrupt_on_signal() -> t.Iterator[None]:
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous_handlers: dict[
        signal.Signals,
        signal.Handlers
        | int
        | t.Callable[[int, types.FrameType | None], object]
        | None,
    ] = {}

    def interrupt(signum: int, frame: types.FrameType | None) -> None:
        raise KeyboardInterrupt

    for name in TERMINATION_SIGNAL_NAMES:
        signum = getattr(signal, name, None)
        if signum is None:
            continue

        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, interrupt)

    try:
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
