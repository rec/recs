import json
import subprocess as sp
import typing as t

from recs.cfg import Cfg
from recs.ui import gui_process


def test_gui_process_writes_rows_to_subprocess_stdin(
    monkeypatch: t.Any,
) -> None:
    processes: list[FakeProcess] = []

    def make_process(*args: object, **kwargs: object) -> FakeProcess:
        process = FakeProcess(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(gui_process.sp, 'Popen', make_process)

    display = gui_process.GuiProcess(
        lambda: iter([{'time': 1}, {'device': 'Mic'}]),
        Cfg(gui=True, ui_refresh_rate=12),
    )
    display.start()

    assert processes[0].args == [
        gui_process.sys.executable,
        '-m',
        'recs.ui.gui_child',
    ]
    assert processes[0].kwargs['stderr'] == sp.DEVNULL
    assert processes[0].kwargs['text'] is True
    assert processes[0].kwargs['env']['RECS_GUI_REFRESH_RATE'] == '12.0'
    assert json.loads(processes[0].stdin.text) == [
        {'time': 1},
        {'device': 'Mic'},
    ]


def test_gui_process_stops_when_subprocess_exits(
    monkeypatch: t.Any,
) -> None:
    processes: list[FakeProcess] = []

    def make_process(*args: object, **kwargs: object) -> FakeProcess:
        process = FakeProcess(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(gui_process.sp, 'Popen', make_process)

    display = gui_process.GuiProcess(lambda: iter([{'time': 1}]), Cfg(gui=True))
    display.start()
    assert not display.closed

    processes[0].returncode = 0

    assert display.closed


def test_gui_process_closes_stdin_on_stop(
    monkeypatch: t.Any,
) -> None:
    processes: list[FakeProcess] = []

    def make_process(*args: object, **kwargs: object) -> FakeProcess:
        process = FakeProcess(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(gui_process.sp, 'Popen', make_process)

    display = gui_process.GuiProcess(lambda: iter([{'time': 1}]), Cfg(gui=True))
    display.start()
    display.stop()

    assert processes[0].stdin.closed


class FakeStdin:
    def __init__(self) -> None:
        self.text = ''
        self.closed = False

    def write(self, text: str) -> int:
        self.text += text
        return len(text)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self.args = list(args[0]) if args else []
        self.kwargs = kwargs
        self.stdin = FakeStdin()
        self.returncode: int | None = None
        self.terminated = False

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
