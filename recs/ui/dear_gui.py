import sys
import time
import typing as t
from pathlib import Path

from threa import Runnable

from recs.cfg import Cfg

from . import presentation

WINDOW = 'recs_window'
TABLE = 'recs_table'
THEME = 'recs_light_theme'
FONT_SIZE = 18
FONT_SCALE = 1.15
FONT_PATHS = [
    Path('/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
    Path('/System/Library/Fonts/Supplemental/Helvetica Bold.ttf'),
    Path('/Library/Fonts/Arial Bold.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
    Path('C:/Windows/Fonts/arialbd.ttf'),
]

COLORS = {
    '': [32, 32, 32, 255],
    'active': [0, 112, 0, 255],
    'offline': [176, 0, 0, 255],
    'volume-low': [0, 112, 0, 255],
    'volume-high': [160, 96, 0, 255],
}


class Context(t.Protocol):
    def __enter__(self) -> object: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None: ...


class DearPyGui(t.Protocol):
    mvAll: int
    mvThemeCat_Core: int
    mvThemeCol_Border: int
    mvThemeCol_ChildBg: int
    mvThemeCol_Header: int
    mvThemeCol_HeaderActive: int
    mvThemeCol_HeaderHovered: int
    mvThemeCol_PopupBg: int
    mvThemeCol_ScrollbarBg: int
    mvThemeCol_TableBorderLight: int
    mvThemeCol_TableBorderStrong: int
    mvThemeCol_TableHeaderBg: int
    mvThemeCol_TableRowBg: int
    mvThemeCol_TableRowBgAlt: int
    mvThemeCol_Text: int
    mvThemeCol_TitleBg: int
    mvThemeCol_TitleBgActive: int
    mvThemeCol_WindowBg: int
    mvStyleVar_CellPadding: int
    mvStyleVar_FramePadding: int
    mvStyleVar_WindowPadding: int

    def create_context(self) -> None: ...

    def create_viewport(self, *, title: str, width: int, height: int) -> None: ...

    def window(self, **kwargs: object) -> Context: ...

    def add_text(self, text: str, *, color: list[int] | None = None) -> None: ...

    def font_registry(self) -> Context: ...

    def add_font(self, file: str, size: float) -> int | str: ...

    def bind_font(self, font: int | str) -> None: ...

    def set_global_font_scale(self, scale: float) -> None: ...

    def theme(self, *, tag: str) -> Context: ...

    def theme_component(self, target: int) -> Context: ...

    def add_theme_color(
        self, target: int, value: list[int], *, category: int
    ) -> int | str: ...

    def add_theme_style(
        self, target: int, x: float, y: float = -1, *, category: int
    ) -> int | str: ...

    def bind_theme(self, theme: str) -> None: ...

    def does_item_exist(self, tag: str) -> bool: ...

    def delete_item(self, tag: str) -> None: ...

    def table(self, **kwargs: object) -> Context: ...

    def add_table_column(self, *, label: str) -> None: ...

    def table_row(self) -> Context: ...

    def table_cell(self) -> Context: ...

    def set_frame_callback(self, frame: int, callback: object) -> None: ...

    def set_primary_window(self, window: str, value: bool) -> None: ...

    def setup_dearpygui(self) -> None: ...

    def show_viewport(self) -> None: ...

    def start_dearpygui(self) -> None: ...

    def stop_dearpygui(self) -> None: ...

    def destroy_context(self) -> None: ...

    def get_frame_count(self) -> int: ...


class Gui(Runnable):
    def __init__(
        self,
        rows: t.Callable[[], t.Iterator[t.Mapping[str, object]]],
        cfg: Cfg,
        *,
        stop_when: t.Callable[[], bool] | None = None,
    ) -> None:
        self.rows = rows
        self.cfg = cfg
        self.stop_when = stop_when
        self.enabled = not cfg.console.silent
        self.dpg = _import_dearpygui() if self.enabled else None
        self._context_ready = False
        self._next_update = 0.0
        super().__init__()

    def update(self) -> None:
        pass

    @property
    def _dpg(self) -> DearPyGui:
        assert self.dpg is not None
        return self.dpg

    def run(self) -> None:
        if not self.enabled:
            return
        super().start()
        try:
            self._run()
        finally:
            super().stop()

    def start(self) -> None:
        self.run()

    def stop(self) -> None:
        if self.enabled and self._context_ready:
            self._dpg.stop_dearpygui()
        super().stop()

    def _run(self) -> None:
        dpg = self._dpg
        dpg.create_context()
        self._context_ready = True
        try:
            dpg.create_viewport(title='recs', width=1024, height=640)
            self._configure_font()
            self._configure_theme()
            with dpg.window(
                label='recs',
                tag=WINDOW,
                no_title_bar=True,
                no_move=True,
                no_resize=True,
                no_collapse=True,
                no_close=True,
                no_scrollbar=True,
            ):
                pass
            dpg.set_primary_window(WINDOW, True)
            self._draw()
            dpg.set_frame_callback(1, self._refresh)
            dpg.setup_dearpygui()
            dpg.show_viewport()
            dpg.start_dearpygui()
        finally:
            dpg.destroy_context()
            self._context_ready = False

    def _configure_font(self) -> None:
        dpg = self._dpg
        dpg.set_global_font_scale(FONT_SCALE)
        for path in FONT_PATHS:
            if not path.exists():
                continue
            with dpg.font_registry():
                font = dpg.add_font(str(path), FONT_SIZE)
            dpg.bind_font(font)
            return

    def _configure_theme(self) -> None:
        dpg = self._dpg
        with dpg.theme(tag=THEME):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(
                    dpg.mvThemeCol_WindowBg,
                    [248, 248, 246, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_ChildBg,
                    [248, 248, 246, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_PopupBg,
                    [248, 248, 246, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_Text,
                    [32, 32, 32, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_Border,
                    [196, 196, 188, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_TableHeaderBg,
                    [226, 226, 218, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_TableRowBg,
                    [255, 255, 252, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_TableRowBgAlt,
                    [240, 240, 234, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_TableBorderStrong,
                    [176, 176, 168, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_TableBorderLight,
                    [212, 212, 204, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_Header,
                    [224, 224, 216, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_HeaderHovered,
                    [214, 214, 206, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_HeaderActive,
                    [204, 204, 196, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_TitleBg,
                    [248, 248, 246, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_TitleBgActive,
                    [248, 248, 246, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_color(
                    dpg.mvThemeCol_ScrollbarBg,
                    [238, 238, 232, 255],
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_style(
                    dpg.mvStyleVar_WindowPadding,
                    12,
                    12,
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_style(
                    dpg.mvStyleVar_FramePadding,
                    8,
                    6,
                    category=dpg.mvThemeCat_Core,
                )
                dpg.add_theme_style(
                    dpg.mvStyleVar_CellPadding,
                    10,
                    8,
                    category=dpg.mvThemeCat_Core,
                )
        dpg.bind_theme(THEME)

    def _refresh(self) -> None:
        if not self.running:
            return
        if self.stop_when and self.stop_when():
            self.stop()
            return
        now = time.monotonic()
        if now >= self._next_update:
            self._draw()
            self._next_update = now + 1 / self.cfg.console.ui_refresh_rate
        dpg = self._dpg
        dpg.set_frame_callback(dpg.get_frame_count() + 1, self._refresh)

    def _draw(self) -> None:
        dpg = self._dpg
        view = presentation.view_model(self.rows())
        if dpg.does_item_exist(TABLE):
            dpg.delete_item(TABLE)

        with dpg.table(
            width=-1,
            height=-1,
            header_row=True,
            row_background=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
            resizable=True,
            scrollY=True,
            parent=WINDOW,
            tag=TABLE,
        ):
            for column in view.columns:
                dpg.add_table_column(label=column)
            for row in view.rows:
                with dpg.table_row():
                    for cell in row.cells:
                        with dpg.table_cell():
                            dpg.add_text(
                                cell.text,
                                color=COLORS.get(cell.style, COLORS['']),
                            )


def _import_dearpygui() -> DearPyGui:
    try:
        import dearpygui.dearpygui as dpg
    except ModuleNotFoundError:
        sys.exit('Dear PyGui is required for --gui')
    return t.cast(DearPyGui, dpg)
