"""A plain resizable Qt window (app_id / WM_CLASS "filler") that a tiling WM must tile.
Started before GifPop so the workspace already has a tiled container."""
import sys

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QLabel

QGuiApplication.setDesktopFileName("filler")
app = QApplication(sys.argv[:1])
app.setApplicationName("filler")
w = QLabel("tiled filler window")
w.setWindowTitle("filler")
w.resize(300, 200)
w.show()
sys.exit(app.exec())
