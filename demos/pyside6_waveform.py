import sys

from PySide6 import QtCore, QtGui, QtWidgets
from waveform_source import FRAME_MS, WINDOW_HEIGHT, WINDOW_WIDTH, WaveformSource


class WaveformWidget(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.source = WaveformSource()
        self.x_values: list[float] = []
        self.y_values: list[float] = []
        self.left = 0.0
        self.right = 2.0
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(FRAME_MS)

    def refresh(self) -> None:
        self.x_values, self.y_values, self.left, self.right = self.source.read()
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(12, 14, 20))
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor(58, 72, 94), 1))
        middle = self.height() / 2
        painter.drawLine(0, round(middle), self.width(), round(middle))

        if len(self.x_values) < 2:
            return

        path = QtGui.QPainterPath()
        path.moveTo(self._x(self.x_values[0]), self._y(self.y_values[0]))
        samples = zip(self.x_values[1:], self.y_values[1:], strict=False)
        for sample_time, sample in samples:
            path.lineTo(self._x(sample_time), self._y(sample))

        painter.setPen(QtGui.QPen(QtGui.QColor(90, 220, 255), 2))
        painter.drawPath(path)

    def _x(self, sample_time: float) -> float:
        return (sample_time - self.left) / (self.right - self.left) * self.width()

    def _y(self, sample: float) -> float:
        return self.height() * (0.5 - sample * 0.45)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = QtWidgets.QMainWindow()
    window.setWindowTitle('PySide6 waveform demo')
    window.setCentralWidget(WaveformWidget())
    window.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
