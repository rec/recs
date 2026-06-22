import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from recs.base.types import Active, RecordKeys  # noqa: E402
from recs.cfg import Cfg  # noqa: E402
from recs.ui import pyside_gui  # noqa: E402
from recs.ui.key_events import KeyEvent  # noqa: E402


def test_pyside_gui_updates_table_rows() -> None:
    _application()
    window = pyside_gui.RecsWindow(Cfg(gui=True))

    window.update_rows(
        [
            {
                'time': 1.25,
                'device': 'Mic',
                'channel': '1',
                'on': Active.active,
                'volume': 0.5,
            }
        ]
    )

    assert window.table.rowCount() == 1
    assert window.table.columnCount() == 8
    assert window.table.item(0, 1).text() == 'Mic'
    assert window.table.item(0, 2).text() == ' 1 '
    assert window.table.item(0, 3).text() == '•'
    assert window.table.item(0, 7).text() == ' 50.0%'


def test_pyside_gui_records_key_press_and_release() -> None:
    _application()
    events: list[KeyEvent] = []
    window = pyside_gui.RecsWindow(
        Cfg(gui=True, record_keys=RecordKeys.all),
        record_key=events.append,
    )

    press = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyPress,
        QtCore.Qt.Key.Key_G,
        QtCore.Qt.KeyboardModifier.NoModifier,
        'g',
    )
    release = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyRelease,
        QtCore.Qt.Key.Key_G,
        QtCore.Qt.KeyboardModifier.NoModifier,
        'g',
    )

    window.keyPressEvent(press)
    window.keyReleaseEvent(release)

    assert [event.model_dump() for event in events] == [
        {'type': 'key_pressed', 'key': 'g'},
        {'type': 'key_released', 'key': 'g'},
    ]


def test_pyside_gui_omits_key_release_in_press_mode() -> None:
    _application()
    events: list[KeyEvent] = []
    window = pyside_gui.RecsWindow(
        Cfg(gui=True, record_keys=RecordKeys.press),
        record_key=events.append,
    )
    release = QtGui.QKeyEvent(
        QtCore.QEvent.Type.KeyRelease,
        QtCore.Qt.Key.Key_G,
        QtCore.Qt.KeyboardModifier.NoModifier,
        'g',
    )

    window.keyReleaseEvent(release)

    assert events == []


def _application() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is not None:
        return app
    return QtWidgets.QApplication([])
