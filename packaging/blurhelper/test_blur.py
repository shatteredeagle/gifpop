"""Manual smoke test for libgifpopblur.so (closes itself after ~2 s).

Run with the build venv's Python (bundled PyQt6-Qt6, same Qt as the helper):
    WAYLAND_DEBUG=client python packaging/blurhelper/test_blur.py path/to/libgifpopblur.so 2>&1 \
        | grep -E 'background_effect|kwin_blur|set_blur_region|set_region|commit|^TEST'
    QT_QPA_PLATFORM=offscreen python packaging/blurhelper/test_blur.py path/to/libgifpopblur.so
"""
import ctypes
import sys

from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QWidget


def log(msg):
    print(f"TEST {msg}", file=sys.stderr, flush=True)


class Win(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(320, 200)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 30, 40, 110))
        p.drawRoundedRect(self.rect(), 12, 12)


def main():
    lib = ctypes.CDLL(sys.argv[1])
    lib.gifpop_blur.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.gifpop_blur.restype = ctypes.c_int

    app = QApplication(sys.argv)
    log(f"platform={app.platformName()}")
    w = Win()
    w.show()

    def call(enable, label):
        ptr = sip.unwrapinstance(w.windowHandle())
        log(f"{label}: gifpop_blur(enable={enable}) -> {lib.gifpop_blur(ptr, enable, 12)}")

    def resize():
        w.resize(420, 260)
        call(1, "after resize 420x260")

    QTimer.singleShot(300, lambda: call(1, "enable"))
    QTimer.singleShot(900, resize)
    QTimer.singleShot(1500, lambda: call(0, "disable"))
    QTimer.singleShot(2000, app.quit)
    app.exec()
    log("exit ok")


if __name__ == "__main__":
    main()
