import sys
import typing as t

from PySide6 import QtCore, QtGui, QtWidgets
from threa import Runnable

from recs.base.types import RecordKeys
from recs.cfg import Cfg

from . import presentation
from .key_events import KeyEvent

FONT_SIZE = 18
UPDATE_INTERVAL_MINIMUM_MS = 1

COLORS = {
    '': (32, 32, 32),
    'active': (0, 112, 0),
    'offline': (176, 0, 0),
    'volume-low': (0, 112, 0),
    'volume-high': (160, 96, 0),
}

STYLE = """
QWidget {
    background: #f8f8f6;
    color: #202020;
}
QTableWidget {
    background: #fffefc;
    alternate-background-color: #f0f0ea;
    gridline-color: #d4d4cc;
    color: #202020;
}
QHeaderView::section {
    background: #e2e2da;
    color: #202020;
    padding: 8px;
    border: 1px solid #b0b0a8;
}
"""


class Gui(Runnable):
    def __init__(
        self,
        rows: t.Callable[[], t.Iterator[t.Mapping[str, object]]],
        cfg: Cfg,
        *,
        stop_when: t.Callable[[], bool] | None = None,
        record_key: t.Callable[[KeyEvent], None] | None = None,
    ) -> None:
        self.rows = rows
        self.cfg = cfg
        self.stop_when = stop_when
        self.record_key = record_key
        self.enabled = not cfg.console.silent
        self.app: QtWidgets.QApplication | None = None
        self.window: RecsWindow | None = None
        self.timer: QtCore.QTimer | None = None
        super().__init__()

    def update(self) -> None:
        if self.window is not None:
            self.window.update_rows(self.rows())

    def run(self) -> None:
        if not self.enabled:
            return

        super().start()
        try:
            app = _application()
            app.setStyleSheet(STYLE)
            self.app = app
            self.window = RecsWindow(self.cfg, record_key=self.record_key)
            self.window.update_rows(self.rows())
            self.window.show()
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(self._refresh)
            self.timer.start(self._update_interval_ms())
            app.exec()
        finally:
            super().stop()
            self.timer = None
            self.window = None

    def start(self) -> None:
        self.run()

    def stop(self) -> None:
        if self.app is not None:
            self.app.quit()
        super().stop()

    def _refresh(self) -> None:
        if not self.running:
            self.stop()
            return
        if self.stop_when and self.stop_when():
            self.stop()
            return
        self.update()

    def _update_interval_ms(self) -> int:
        rate = self.cfg.console.ui_refresh_rate
        return max(UPDATE_INTERVAL_MINIMUM_MS, round(1000 / rate))


class RecsWindow(QtWidgets.QWidget):
    def __init__(
        self,
        cfg: Cfg,
        *,
        record_key: t.Callable[[KeyEvent], None] | None = None,
    ) -> None:
        super().__init__()
        self.cfg = cfg
        self.record_key = record_key
        self.setWindowTitle('recs')
        self.resize(1024, 640)
        self.setFont(QtGui.QFont('', FONT_SIZE, QtGui.QFont.Weight.Bold))
        self.table = QtWidgets.QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setColumnCount(len(presentation.COLUMNS))
        self.table.setHorizontalHeaderLabels(presentation.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.table)

    def update_rows(self, rows: t.Iterable[t.Mapping[str, object]]) -> None:
        view = presentation.view_model(rows)
        self.table.setColumnCount(len(view.columns))
        self.table.setHorizontalHeaderLabels(view.columns)
        self.table.setRowCount(len(view.rows))
        for row_number, row in enumerate(view.rows):
            for column_number, cell in enumerate(row.cells):
                item = QtWidgets.QTableWidgetItem(cell.text)
                item.setForeground(
                    QtGui.QBrush(QtGui.QColor(*COLORS.get(cell.style, COLORS[''])))
                )
                self.table.setItem(row_number, column_number, item)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if (
            self.record_key is not None
            and self.cfg.keys.record_keys != RecordKeys.none
            and not event.isAutoRepeat()
        ):
            self.record_key(KeyEvent(type='key_pressed', key=_key_name(event)))
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if (
            self.record_key is not None
            and self.cfg.keys.record_keys == RecordKeys.all
            and not event.isAutoRepeat()
        ):
            self.record_key(KeyEvent(type='key_released', key=_key_name(event)))
        super().keyReleaseEvent(event)


def _application() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is not None:
        return t.cast(QtWidgets.QApplication, app)
    return QtWidgets.QApplication(sys.argv[:1])


def _key_name(event: QtGui.QKeyEvent) -> str:
    text = event.text()
    if len(text) == 1 and text.isprintable():
        return text.lower()

    try:
        key = QtCore.Qt.Key(event.key())
    except ValueError:
        return str(event.key())
    return key.name.removeprefix('Key_')
