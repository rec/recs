import types
from pathlib import Path

import pytest

from recs.cfg import Cfg
from recs.ui import dear_gui


def test_gui_is_disabled_in_silent_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dear_gui, '_import_dearpygui', _fake_dearpygui)

    gui = dear_gui.Gui(lambda: iter(()), Cfg(gui=True, silent=True))

    assert not gui.enabled


def test_gui_runs_dearpygui_on_current_thread(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = _fake_dearpygui()
    font = tmp_path / 'bold.ttf'
    font.touch()
    monkeypatch.setattr(dear_gui, 'FONT_PATHS', [font])
    monkeypatch.setattr(dear_gui, '_import_dearpygui', lambda: fake)

    gui = dear_gui.Gui(lambda: iter(()), Cfg(gui=True))
    gui.run()

    assert fake.started
    assert fake.font_bound == 'bold-font'
    assert fake.font_file == str(font)
    assert fake.font_scale == dear_gui.FONT_SCALE
    assert fake.font_size == dear_gui.FONT_SIZE
    assert fake.thread_name == 'MainThread'
    assert fake.primary_window == dear_gui.WINDOW
    assert fake.theme_bound == dear_gui.THEME
    assert fake.window_kwargs == {
        'label': 'recs',
        'tag': dear_gui.WINDOW,
        'no_title_bar': True,
        'no_move': True,
        'no_resize': True,
        'no_collapse': True,
        'no_close': True,
        'no_scrollbar': True,
    }
    assert fake.table_kwargs['width'] == -1
    assert fake.table_kwargs['height'] == -1
    assert fake.table_kwargs['row_background']
    assert fake.table_kwargs['scrollY']


class FakeDearPyGui(types.SimpleNamespace):
    mvAll: int = 1
    mvThemeCat_Core: int = 2
    mvThemeCol_Border: int = 3
    mvThemeCol_ChildBg: int = 4
    mvThemeCol_Header: int = 5
    mvThemeCol_HeaderActive: int = 6
    mvThemeCol_HeaderHovered: int = 7
    mvThemeCol_PopupBg: int = 8
    mvThemeCol_ScrollbarBg: int = 9
    mvThemeCol_TableBorderLight: int = 10
    mvThemeCol_TableBorderStrong: int = 11
    mvThemeCol_TableHeaderBg: int = 12
    mvThemeCol_TableRowBg: int = 13
    mvThemeCol_TableRowBgAlt: int = 14
    mvThemeCol_Text: int = 15
    mvThemeCol_TitleBg: int = 16
    mvThemeCol_TitleBgActive: int = 17
    mvThemeCol_WindowBg: int = 18
    mvStyleVar_CellPadding: int = 19
    mvStyleVar_FramePadding: int = 20
    mvStyleVar_WindowPadding: int = 21
    started: bool = False
    thread_name: str = ''
    primary_window: str = ''
    font_bound: str = ''
    font_file: str = ''
    font_scale: float = 0.0
    font_size: float = 0.0
    table_kwargs: dict[str, object]
    theme_bound: str = ''
    window_kwargs: dict[str, object]

    def __init__(self) -> None:
        super().__init__()
        self.table_kwargs = {}
        self.window_kwargs = {}

    def create_context(self) -> None:
        pass

    def create_viewport(self, *, title: str, width: int, height: int) -> None:
        pass

    def window(self, **kwargs: object) -> object:
        self.window_kwargs = kwargs
        return _Context()

    def add_text(self, text: str, *, color: list[int] | None = None) -> None:
        pass

    def font_registry(self) -> object:
        return _Context()

    def add_font(self, file: str, size: float) -> int | str:
        self.font_file = file
        self.font_size = size
        return 'bold-font'

    def bind_font(self, font: int | str) -> None:
        self.font_bound = str(font)

    def set_global_font_scale(self, scale: float) -> None:
        self.font_scale = scale

    def theme(self, *, tag: str) -> object:
        return _Context()

    def theme_component(self, target: int) -> object:
        return _Context()

    def add_theme_color(
        self, target: int, value: list[int], *, category: int
    ) -> int | str:
        return target

    def add_theme_style(
        self, target: int, x: float, y: float = -1, *, category: int
    ) -> int | str:
        return target

    def bind_theme(self, theme: str) -> None:
        self.theme_bound = theme

    def does_item_exist(self, tag: str) -> bool:
        return False

    def delete_item(self, tag: str) -> None:
        pass

    def table(self, **kwargs: object) -> object:
        self.table_kwargs = kwargs
        return _Context()

    def add_table_column(self, *, label: str) -> None:
        pass

    def table_row(self) -> object:
        return _Context()

    def table_cell(self) -> object:
        return _Context()

    def set_frame_callback(self, frame: int, callback: object) -> None:
        pass

    def set_primary_window(self, window: str, value: bool) -> None:
        if value:
            self.primary_window = window

    def setup_dearpygui(self) -> None:
        pass

    def show_viewport(self) -> None:
        pass

    def start_dearpygui(self) -> None:
        import threading

        self.started = True
        self.thread_name = threading.current_thread().name

    def stop_dearpygui(self) -> None:
        pass

    def destroy_context(self) -> None:
        pass

    def get_frame_count(self) -> int:
        return 1


class _Context:
    def __enter__(self) -> None:
        return None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        pass


def _fake_dearpygui() -> FakeDearPyGui:
    return FakeDearPyGui()
